# Movie Dupecheck v2 — Radarr-aware

Finds and removes duplicate movies across an **HD Radarr** and a **UHD Radarr**, and extra video files
sitting inside a movie's folder. Talks to Radarr; never guesses from folder names.

## Why v2

v1 matched movies by folder name and deleted folders behind Radarr's back. Two things went wrong:

1. Radarr still had the movie **monitored**, so it just downloaded it again → an endless loop.
2. Name parsing can't tell a duplicate from a **box set** (`The.Fast.and.the.Furious.Collection…` holds
   8 different films in one folder) — v1 would have kept one and deleted seven movies.

v2 fixes both by using Radarr as the source of truth:

- Movies are matched by **TMDB id** across the two Radarrs.
- Deletion goes **through Radarr's API** (`DELETE /movie?deleteFiles=true&addImportExclusion=true`), so the
  file is removed *and* the movie can never be re-added or re-downloaded.
- For extra files inside a folder, Radarr's **own parser** (`/api/v3/parse`) decides whether a file is the
  same movie (→ duplicate, delete) or a different one (→ box set / bonus film, keep and report).
- **Dry run by default.** Nothing is deleted without `--apply`, and `--apply` asks you to type `DELETE`
  unless you add `--yes` (for cron).

## Rules

**Cross-library** — a movie that has a file in *both* Radarrs:

- The **UHD library is the keeper**. The script never deletes from UHD Radarr (it has to stay so it can keep
  upgrading toward the Dolby Vision remux you actually want).
- The **HD copy is deleted** when UHD's file is at least as good (resolution → source → size).
- If the HD file is *better* than UHD's (HD found a 2160p web, UHD only has a 720p), it is **skipped and
  reported** — let UHD Radarr's upgrade search fix that first. `--force` overrides.

**In-folder** — a movie folder with more than one video file (≥ `--min-size-mb`, default 700 MB):

- Files that Radarr's parser maps to the **same movie** as the folder → deleted, then Radarr rescans.
- Files that map to a **different movie** or don't parse → kept, listed as box-set files.

## Usage

Run on the host that can see the movie folders (Unraid), so the in-folder scan can stat files:

```bash
# dry run (default) — shows exactly what would go
python3 movie_dupecheck.py \
  --hd-url  http://192.168.2.9:7878 --hd-key  <HD api key> \
  --uhd-url http://192.168.2.9:7979 --uhd-key <UHD api key> \
  --path-map /data=/mnt/user/media

# do it
python3 movie_dupecheck.py ... --apply          # asks you to type DELETE
python3 movie_dupecheck.py ... --apply --yes    # for cron
```

Keys can also come from the environment: `HD_URL`, `HD_KEY`, `UHD_URL`, `UHD_KEY`.

| Flag | Meaning |
|---|---|
| `--path-map C=H` | container path prefix → host prefix (Radarr reports `/data/...`; the host sees `/mnt/user/media/...`). Repeatable. Without it the in-folder pass is skipped. |
| `--min-size-mb N` | ignore video files smaller than N MB (samples, trailers). Default 700. |
| `--skip-cross` / `--skip-folders` | run only one of the two passes |
| `--force` | delete the HD copy even when it is better than the UHD file |
| `--apply` | actually delete (otherwise dry run) |
| `--yes` | with `--apply`: no interactive confirmation |

## Example (dry run)

```
mode: DRY RUN   rule: UHD is the keeper; HD copy goes when UHD's file is as good or better

== movies with a file in BOTH libraries: 39
  DELETE HD    2.0 GB WEBDL-1080p   | keep UHD   77.8 GB Remux-2160p   | Backrooms (2026)
  DELETE HD    1.8 GB Bluray-1080p  | keep UHD   61.6 GB Remux-2160p   | Dangerous Animals (2025)
  SKIP   HD   13.6 GB WEBDL-2160p   is BETTER than UHD    1.3 GB WEBDL-720p | Deep Water (2026)  <- let UHD Radarr upgrade first (or --force)
  -> 38 HD copies,  580.2 GB to free; 1 skipped

== HD: folders with extra video files
  DELETE    6.9 GB Civil War 2024 1080p ... HEVC-NmCT.mkv   (Radarr keeps: Civil.War.2024.2160p...AOC.mkv)
  KEEP     4.1 GB Fast.Five.2011...mkv   <- parses as a DIFFERENT movie (box set / bonus film)
```

## Requirements

Python 3.8+, standard library only. Radarr v3 API (Radarr 4/5/6).

## License

MIT
