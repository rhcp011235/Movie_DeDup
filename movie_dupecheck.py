#!/usr/bin/env python3
"""
Movie Dupecheck v2 — Radarr-aware, TMDB-matched, safe by default.

What it does
  1. CROSS-LIBRARY: a movie that has a file in BOTH the HD Radarr and the UHD Radarr
     -> the loser is deleted THROUGH Radarr (movie + file + import-exclusion),
        so Radarr never re-downloads it and never re-adds it from a list.
  2. IN-FOLDER: a movie folder holding more than one video file
     -> extra files are deleted only if Radarr's own parser says they are the SAME
        movie (box sets / collections / bonus films are reported, never touched).

Why v1 "never worked right": it matched by folder name and deleted behind Radarr's
back, so Radarr (movie still monitored) simply downloaded it again — and one parse
miss on a collection folder would delete real movies.

Everything is a dry run unless you pass --apply.

Standard library only. Talks to Radarr over its HTTP API (v3).
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".iso", ".wmv"}


# ----------------------------------------------------------------------------- Radarr client
class Radarr:
    def __init__(self, name, url, key):
        self.name, self.url, self.key = name, url.rstrip("/"), key

    def _req(self, method, path, params=None, body=None):
        q = "?" + urllib.parse.urlencode(params) if params else ""
        req = urllib.request.Request(f"{self.url}/api/v3/{path}{q}", method=method,
                                     headers={"X-Api-Key": self.key, "Content-Type": "application/json"})
        data = json.dumps(body).encode() if body is not None else None
        with urllib.request.urlopen(req, data=data, timeout=120) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    def movies(self):
        return self._req("GET", "movie")

    def parse(self, title):
        """Ask Radarr what movie a release/file name refers to. Returns tmdbId or None."""
        try:
            r = self._req("GET", "parse", {"title": title})
            m = (r or {}).get("movie") or {}
            return m.get("tmdbId")
        except Exception:
            return None

    def delete_movie(self, movie_id, delete_files=True, exclude=True):
        return self._req("DELETE", f"movie/{movie_id}",
                         {"deleteFiles": str(delete_files).lower(), "addImportExclusion": str(exclude).lower()})

    def rescan(self, movie_id):
        return self._req("POST", "command", body={"name": "RescanMovie", "movieId": movie_id})

    def root_folders(self):
        return [r["path"] for r in self._req("GET", "rootfolder")]


# ----------------------------------------------------------------------------- helpers
def gb(n):
    return f"{n / 1e9:6.1f} GB"


def map_path(container_path, path_map):
    """Translate a Radarr (container) path to a host path using --path-map /data=/mnt/user/media."""
    for src, dst in path_map:
        if container_path == src or container_path.startswith(src.rstrip("/") + "/"):
            return dst.rstrip("/") + container_path[len(src.rstrip("/")):]
    return container_path


def quality_rank(mf):
    q = mf["quality"]["quality"]
    # resolution first (2160 > 1080 ...), then remux > bluray > web. Size is NOT a tiebreaker:
    # two 2160p remuxes are "equal" and the UHD library keeps its copy.
    src = {"remux": 3, "bluray": 2, "webdl": 1, "webrip": 1}.get(q.get("source", "").lower(), 0)
    return (q.get("resolution", 0), src)


# ----------------------------------------------------------------------------- cross-library
def cross_library(hd, uhd, force):
    """Movies with a file in both libraries.

    The UHD library is the keeper: we NEVER delete from UHD Radarr (it must stay so it can
    keep upgrading toward DV). The HD copy is deleted when UHD's file is at least as good
    (resolution > source > size). If the HD file is *better* than UHD's (e.g. HD has a 2160p
    web and UHD only found a 720p), it is SKIPPED and reported — UHD Radarr's own upgrade
    search should fix that side first. --force deletes the HD copy regardless.
    Returns (deletions, skipped): deletions = [(hd, hd_movie, uhd_movie)], skipped = same shape.
    """
    h = {m["tmdbId"]: m for m in hd.movies() if m.get("hasFile") and m.get("movieFile")}
    u = {m["tmdbId"]: m for m in uhd.movies() if m.get("hasFile") and m.get("movieFile")}
    dele, skip = [], []
    for t in sorted(set(h) & set(u), key=lambda t: h[t]["title"]):
        hm, um = h[t], u[t]
        if force or quality_rank(um["movieFile"]) >= quality_rank(hm["movieFile"]):
            dele.append((hd, hm, um))
        else:
            skip.append((hd, hm, um))
    return dele, skip


# ----------------------------------------------------------------------------- in-folder duplicates
def in_folder_duplicates(radarr, path_map, min_bytes):
    """For each movie folder with >1 video file, classify the untracked ones."""
    dups, boxsets, review = [], [], []
    for m in radarr.movies():
        mf = m.get("movieFile")
        if not mf or not m.get("path"):
            continue
        host_dir = map_path(m["path"], path_map)
        if not os.path.isdir(host_dir):
            continue
        tracked = os.path.normpath(os.path.join(host_dir, mf["relativePath"]))
        videos = []
        for root, _dirs, files in os.walk(host_dir):
            for f in files:
                p = os.path.join(root, f)
                if os.path.splitext(f)[1].lower() in VIDEO_EXT and os.path.getsize(p) >= min_bytes:
                    videos.append(os.path.normpath(p))
        if len(videos) < 2:
            continue
        for p in videos:
            if p == tracked:
                continue
            parsed = radarr.parse(os.path.basename(p))
            entry = (m, p, os.path.getsize(p), tracked)
            if parsed != m["tmdbId"]:
                boxsets.append(entry)       # different movie or unparseable -> report only
            elif os.path.splitext(tracked)[1].lower() in (".m2ts", ".iso") and os.path.splitext(p)[1].lower() == ".mkv":
                review.append(entry)        # Radarr tracks a disc image but a proper .mkv sits next to it: the WRONG one would go
            else:
                dups.append(entry)          # same movie, not the file Radarr tracks -> duplicate
    return dups, boxsets, review


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Radarr-aware movie de-duplicator (dry run unless --apply).")
    ap.add_argument("--hd-url", default=os.environ.get("HD_URL", "http://192.168.2.9:7878"))
    ap.add_argument("--hd-key", default=os.environ.get("HD_KEY"))
    ap.add_argument("--uhd-url", default=os.environ.get("UHD_URL", "http://192.168.2.9:7979"))
    ap.add_argument("--uhd-key", default=os.environ.get("UHD_KEY"))
    ap.add_argument("--force", action="store_true",
                    help="delete the HD copy even when it is better than the UHD file (default: skip those)")
    ap.add_argument("--path-map", action="append", default=[],
                    help="container=host path prefix, e.g. /data=/mnt/user/media (needed for in-folder scan)")
    ap.add_argument("--min-size-mb", type=int, default=700, help="ignore video files smaller than this (samples/trailers)")
    ap.add_argument("--skip-cross", action="store_true", help="don't do the HD/UHD cross-library pass")
    ap.add_argument("--skip-folders", action="store_true", help="don't do the in-folder duplicate pass")
    ap.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    ap.add_argument("--yes", action="store_true", help="with --apply: don't ask for the DELETE confirmation (cron)")
    a = ap.parse_args()
    if not a.hd_key or not a.uhd_key:
        sys.exit("need --hd-key/--uhd-key (or HD_KEY/UHD_KEY env)")
    path_map = [tuple(x.split("=", 1)) for x in a.path_map if "=" in x]
    hd, uhd = Radarr("HD", a.hd_url, a.hd_key), Radarr("UHD", a.uhd_url, a.uhd_key)

    plan_cross, plan_files, keep = [], [], []
    print(f"mode: {'APPLY' if a.apply else 'DRY RUN'}   rule: UHD is the keeper; HD copy goes when UHD's file is as good or better\n")

    if not a.skip_cross:
        dele, skip = cross_library(hd, uhd, a.force)
        print(f"== movies with a file in BOTH libraries: {len(dele) + len(skip)}")
        for r, hm, um in dele:
            hf, uf = hm["movieFile"], um["movieFile"]
            print(f"  DELETE HD {gb(hf['size'])} {hf['quality']['quality']['name']:13} | keep UHD {gb(uf['size'])} "
                  f"{uf['quality']['quality']['name']:13} | {hm['title']} ({hm['year']})")
            plan_cross.append((r, hm))
        for r, hm, um in skip:
            hf, uf = hm["movieFile"], um["movieFile"]
            print(f"  SKIP   HD {gb(hf['size'])} {hf['quality']['quality']['name']:13} is BETTER than UHD {gb(uf['size'])} "
                  f"{uf['quality']['quality']['name']:13} | {hm['title']} ({hm['year']})  <- let UHD Radarr upgrade first (or --force)")
        print(f"  -> {len(plan_cross)} HD copies, {gb(sum(m['movieFile']['size'] for _, m in plan_cross))} to free; {len(skip)} skipped\n")

    if not a.skip_folders:
        if not path_map:
            print("== in-folder scan skipped: pass --path-map /data=/mnt/user/media (run on the Unraid host)\n")
        else:
            for r in (hd, uhd):
                dups, boxsets, review = in_folder_duplicates(r, path_map, a.min_size_mb * 1024 * 1024)
                print(f"== {r.name}: folders with extra video files")
                for m, p, size, tracked in dups:
                    print(f"  DELETE {gb(size)} {os.path.basename(p)}   (Radarr keeps: {os.path.basename(tracked)})")
                    plan_files.append((r, m, p, size))
                for m, p, size, tracked in review:
                    print(f"  REVIEW {gb(size)} {os.path.basename(p)}   <- Radarr tracks the disc image {os.path.basename(tracked)}; "
                          f"import this .mkv in Radarr (Manual Import) so the disc becomes the extra, then re-run")
                for m, p, size, tracked in boxsets:
                    print(f"  KEEP   {gb(size)} {os.path.basename(p)}   <- parses as a DIFFERENT movie (box set / bonus film)")
                    keep.append(p)
                print(f"  -> {len(dups)} duplicate files, {gb(sum(x[2] for x in dups))} to free; {len(boxsets)} box-set files left alone\n")

    total = len(plan_cross) + len(plan_files)
    if total == 0:
        print("nothing to do.")
        return
    if not a.apply:
        print(f"[DRY RUN] would delete {total} items. Re-run with --apply to do it.")
        return
    if not a.yes:
        if input(f"Type DELETE to remove {total} items: ").strip() != "DELETE":
            print("cancelled."); return

    done = 0
    for r, m in plan_cross:
        try:
            r.delete_movie(m["id"], delete_files=True, exclude=True)
            print(f"  deleted from {r.name} + excluded: {m['title']} ({m['year']})"); done += 1
        except Exception as e:
            print(f"  FAILED {r.name} {m['title']}: {e}")
    for r, m, p, _ in plan_files:
        try:
            os.remove(p); r.rescan(m["id"])
            print(f"  removed extra file: {os.path.basename(p)}"); done += 1
        except Exception as e:
            print(f"  FAILED {p}: {e}")
    print(f"\ndone: {done}/{total}")


if __name__ == "__main__":
    main()
