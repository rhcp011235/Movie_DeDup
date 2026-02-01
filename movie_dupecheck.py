#!/usr/bin/env python3
"""
Movie Dupecheck Script
Finds duplicate movies within HD/UHD lists and movies that exist in both.
Handles various naming conventions and special characters.
Can optionally scan directories for real file sizes.
"""

import re
import os
import argparse
from collections import defaultdict

def parse_movie_list(filepath):
    """Parse a movie list file or directory and return list of movie names."""
    movies = []
    if not filepath:
        return movies
    try:
        if os.path.isdir(filepath):
            for item in os.listdir(filepath):
                if item.startswith('.'):
                    continue
                if item == '@eaDir':
                    continue
                movies.append(item)
        elif os.path.isfile(filepath):
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        line = line.strip()
                        if not line:
                            continue
                        if '|' in line:
                            line = line.split('|', 1)[1]
                        line = line.rstrip('/')
                        line = line.strip()
                        if line and line != r'\@eaDir' and not line.startswith('@'):
                            movies.append(line)
                    except Exception:
                        continue
        else:
            pass
    except (IOError, OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not read {filepath}: {e}")
    return movies

def get_file_size(path, movie_name):
    """Get the largest video file size in a movie directory. Handles nested folders."""
    if not path or not movie_name:
        return 0
    full_path = os.path.join(path, movie_name)
    if not full_path or not os.path.exists(full_path):
        return 0
    video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts', '.iso'}
    max_size = 0
    max_file = ""
    visited_inodes = set()
    try:
        for root, dirs, files in os.walk(full_path, followlinks=False):
            for d in dirs:
                dpath = os.path.join(root, d)
                try:
                    if os.path.islink(dpath):
                        st = os.lstat(dpath)
                        if st.st_ino in visited_inodes:
                            dirs.remove(d)
                            continue
                        visited_inodes.add(st.st_ino)
                except (OSError, IOError):
                    pass
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in video_extensions:
                        continue
                    if os.path.islink(fpath):
                        if not os.path.exists(fpath):
                            continue
                    size = os.path.getsize(fpath)
                    if size > max_size:
                        max_size = size
                        max_file = f
                except (OSError, IOError, ValueError):
                    pass
    except (OSError, IOError):
        pass
    return max_size

def format_size(size):
    """Format bytes to human readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def get_title_year(name):
    """Extract just the title and year from folder name for grouping."""
    if not name or not isinstance(name, str):
        return ""
    
    year = None
    title_end = len(name)
    
    match = re.search(r'\(\s*(\d{4})\s*\)', name)
    if match:
        year = match.group(1)
        title_end = match.start()
    else:
        match = re.search(r'[\.\-\s](\d{4})(?=[\.\-\s]|$)', name)
        if match:
            year = match.group(1)
            title_end = match.start()
    
    title = name[:title_end].strip(' .,-')
    
    if year:
        return f"{title} ({year})"
    return title

def get_core_name(name):
    """Alias for get_title_year for compatibility."""
    return get_title_year(name)

def find_duplicates(movies, category):
    """Find duplicate movies within a single list."""
    normalized_groups = defaultdict(list)
    for movie in movies:
        core = get_core_name(movie)
        normalized_groups[core].append((core, movie))
    duplicates = {}
    for key, movie_list in normalized_groups.items():
        if len(movie_list) > 1:
            first_core = movie_list[0][0]
            duplicates[first_core] = [m[1] for m in movie_list]
    return duplicates

def find_cross_duplicates(hd_movies, uhd_movies):
    """Find movies that exist in both HD and UHD lists."""
    hd_normalized = defaultdict(list)
    for m in hd_movies:
        core = get_core_name(m)
        hd_normalized[core].append(m)
    
    uhd_normalized = defaultdict(list)
    for m in uhd_movies:
        core = get_core_name(m)
        uhd_normalized[core].append(m)
    
    common = set(hd_normalized.keys()) & set(uhd_normalized.keys())
    cross_dupes = {}
    for key in common:
        if len(key) > 3:
            cross_dupes[key] = {
                'hd': hd_normalized[key],
                'uhd': uhd_normalized[key]
            }
    return cross_dupes

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)

def print_duplicates_dry_run(dupes, category, hd_path, uhd_path):
    """Print duplicates in dry run mode showing normalized names and folder paths."""
    path = hd_path if category == "HD" else uhd_path
    for i, (core, movie_list) in enumerate(sorted(dupes.items()), 1):
        title = core.split('(')[0].strip().title()
        print(f"{i}. {title} ({len(movie_list)} copies)")
        print(f"   Normalized ID: {core}")
        for movie in movie_list:
            if path:
                full_path = os.path.join(path, movie)
                exists = "EXISTS" if os.path.exists(full_path) else "NOT FOUND"
            else:
                exists = ""
            print(f"   - {movie} {exists}")
        print()

def print_duplicates_with_sizes(dupes, category, hd_path, uhd_path, interactive=False, delete_callback=None):
    """Print duplicates with file sizes and recommend which to keep."""
    path = hd_path if category == "HD" else uhd_path
    if not path:
        return
    to_delete = []
    for i, (core, movie_list) in enumerate(sorted(dupes.items()), 1):
        title = core.split('(')[0].strip().title()
        print(f"{i}. {title} ({len(movie_list)} copies)")
        file_info = []
        for movie in movie_list:
            if not movie:
                continue
            size = get_file_size(path, movie)
            file_info.append((movie, size))
        file_info.sort(key=lambda x: x[1], reverse=True)
        for j, (movie, size) in enumerate(file_info):
            marker = "  KEEP >" if j == 0 else "  DELETE"
            size_str = format_size(size) if size > 0 else "NOT FOUND"
            print(f"   {marker} {size_str:>12} | {movie}")
            if j > 0:
                to_delete.append((path, movie))
        print()
    return to_delete

def print_cross_duplicates_with_sizes(cross_dupes, hd_path, uhd_path, interactive=False, delete_callback=None):
    """Print movies in both HD and UHD with sizes."""
    if not hd_path or not uhd_path:
        return
    to_delete = []
    for i, (core, versions) in enumerate(sorted(cross_dupes.items()), 1):
        hd_list = versions['hd'] if isinstance(versions['hd'], list) else [versions['hd']]
        uhd_list = versions['uhd'] if isinstance(versions['uhd'], list) else [versions['uhd']]
        
        hd_size = max(get_file_size(hd_path, m) for m in hd_list) if hd_list else 0
        uhd_size = max(get_file_size(uhd_path, m) for m in uhd_list) if uhd_list else 0
        
        keep = "UHD" if uhd_size > hd_size else "HD"
        delete = "HD" if keep == "UHD" else "UHD"
        title = core.split('(')[0].strip().title()
        
        print(f"{i}. {title}")
        print(f"   Normalized ID: {core}")
        print(f"   HD  > {format_size(hd_size):>12} | {hd_list[0]}")
        for m in hd_list[1:]:
            print(f"         {format_size(get_file_size(hd_path, m)):>12} | {m}")
        print(f"   UHD > {format_size(uhd_size):>12} | {uhd_list[0]}")
        for m in uhd_list[1:]:
            print(f"         {format_size(get_file_size(uhd_path, m)):>12} | {m}")
        print(f"   >>> RECOMMEND: Delete {delete} version (keep {keep})")
        
        if delete == "HD":
            for m in hd_list:
                to_delete.append((hd_path, m))
        else:
            for m in uhd_list:
                to_delete.append((uhd_path, m))
        print()
    return to_delete

def get_folder_size(path, folder_name):
    """Get total size of a folder in bytes."""
    if not path or not folder_name:
        return 0
    full_path = os.path.join(path, folder_name)
    if not os.path.exists(full_path):
        return 0
    total_size = 0
    try:
        for root, dirs, files in os.walk(full_path, followlinks=False):
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    if not os.path.islink(fpath):
                        total_size += os.path.getsize(fpath)
                except (OSError, IOError):
                    pass
    except (OSError, IOError):
        pass
    return total_size

def calculate_total_delete_size(to_delete_hd, to_delete_uhd):
    """Calculate total size of all folders to be deleted."""
    total_size = 0
    for path, folder in to_delete_hd + to_delete_uhd:
        total_size += get_folder_size(path, folder)
    return total_size

def confirm_and_delete(to_delete_hd, to_delete_uhd):
    """Ask for confirmation and delete marked folders."""
    hd_count = len(to_delete_hd)
    uhd_count = len(to_delete_uhd)
    total = hd_count + uhd_count
    
    if total == 0:
        print("\nNo folders to delete.")
        return
    
    total_size = calculate_total_delete_size(to_delete_hd, to_delete_uhd)
    
    print(f"\n{'='*60}")
    print(f" READY TO DELETE {total} FOLDERS:")
    print(f" Total space to be freed: {format_size(total_size)}")
    print(f"{'='*60}")
    if hd_count > 0:
        print(f"\n  HD folder ({hd_count} folders):")
        for path, folder in sorted(to_delete_hd):
            print(f"    - {folder}")
    if uhd_count > 0:
        print(f"\n  UHD folder ({uhd_count} folders):")
        for path, folder in sorted(to_delete_uhd):
            print(f"    - {folder}")
    print(f"\n  Total: {total} folders will be DELETED")
    print(f"{'='*60}")
    
    print()
    response = input("  Type 'DELETE' to confirm deletion: ").strip()
    print()
    
    if response != "DELETE":
        print("  Deletion cancelled. No changes made.")
        return
    
    print("  Deleting...")
    deleted = 0
    failed = 0
    
    for path, folder in to_delete_hd + to_delete_uhd:
        full_path = os.path.join(path, folder) if path else folder
        if os.path.exists(full_path):
            try:
                import shutil
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
                print(f"    Deleted: {folder}")
                deleted += 1
            except Exception as e:
                print(f"    FAILED: {folder} - {e}")
                failed += 1
        else:
            print(f"    Not found (already deleted?): {folder}")
    
    print(f"\n  Done! Deleted: {deleted}, Failed: {failed}")

def print_cross_duplicates_dry_run(cross_dupes, hd_path, uhd_path):
    """Print cross duplicates in dry run mode showing normalized names."""
    for i, (core, versions) in enumerate(sorted(cross_dupes.items()), 1):
        title = core.split('(')[0].strip().title()
        print(f"{i}. {title}")
        print(f"   Normalized ID: {core}")
        hd_list = versions['hd'] if isinstance(versions['hd'], list) else [versions['hd']]
        uhd_list = versions['uhd'] if isinstance(versions['uhd'], list) else [versions['uhd']]
        for m in hd_list:
            if hd_path:
                hd_full = os.path.join(hd_path, m)
                hd_exists = "EXISTS" if os.path.exists(hd_full) else "NOT FOUND"
            else:
                hd_exists = ""
            print(f"   HD:  {m} [{hd_exists}]")
        for m in uhd_list:
            if uhd_path:
                uhd_full = os.path.join(uhd_path, m)
                uhd_exists = "EXISTS" if os.path.exists(uhd_full) else "NOT FOUND"
            else:
                uhd_exists = ""
            print(f"   UHD: {m} [{uhd_exists}]")
        print(f"   >>> ACTION: Delete smaller version (keep larger)")
        print()

def main():
    parser = argparse.ArgumentParser(description='Check movie collections for duplicates.')
    parser.add_argument('--hd-file', default='HD', help='Path to HD movie list file')
    parser.add_argument('--uhd-file', default='UHD', help='Path to UHD movie list file')
    parser.add_argument('--hd-path', default='', help='Path to HD directory for size checking')
    parser.add_argument('--uhd-path', default='', help='Path to UHD directory for size checking')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without scanning')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed debug info')
    args = parser.parse_args()
    if not os.path.exists(args.hd_file):
        args.hd_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HD")
    if not os.path.exists(args.uhd_file):
        args.uhd_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UHD")
    if args.verbose and args.hd_path:
        print(f"[DEBUG] HD path: {args.hd_path}")
        print(f"[DEBUG] UHD path: {args.uhd_path}")
        test_path = os.path.join(args.hd_path, os.listdir(args.hd_path)[0]) if os.listdir(args.hd_path) else ""
        if test_path:
            print(f"[DEBUG] Sample HD folder: {test_path}")
            print(f"[DEBUG] Contents: {os.listdir(test_path)[:5]}")
    hd_movies = parse_movie_list(args.hd_file)
    uhd_movies = parse_movie_list(args.uhd_file)
    print_section("MOVIE DUPLICATE CHECK RESULTS")
    print(f"\nTotal HD movies: {len(hd_movies)}")
    print(f"Total UHD movies: {len(uhd_movies)}")
    if args.dry_run:
        print("\n[DRY RUN MODE - No directory scanning]")
    hd_dupes = find_duplicates(hd_movies, "HD")
    uhd_dupes = find_duplicates(uhd_movies, "UHD")
    cross_dupes = find_cross_duplicates(hd_movies, uhd_movies)
    
    to_delete_hd = []
    to_delete_uhd = []
    
    print_section("MOVIES IN BOTH HD AND UHD")
    if cross_dupes:
        print(f"\nFound {len(cross_dupes)} movies that exist in both HD and UHD:\n")
        if args.hd_path and args.uhd_path and not args.dry_run:
            cross_del = print_cross_duplicates_with_sizes(cross_dupes, args.hd_path, args.uhd_path)
            if cross_del:
                for path, folder in cross_del:
                    if path == args.hd_path:
                        to_delete_hd.append((path, folder))
                    else:
                        to_delete_uhd.append((path, folder))
        elif args.dry_run:
            print_cross_duplicates_dry_run(cross_dupes, args.hd_path, args.uhd_path)
        else:
            for i, (core, versions) in enumerate(sorted(cross_dupes.items()), 1):
                title = core.split('(')[0].strip().title()
                print(f"{i}. {title}")
                print(f"   Normalized ID: {core}")
                hd_list = versions['hd'] if isinstance(versions['hd'], list) else [versions['hd']]
                uhd_list = versions['uhd'] if isinstance(versions['uhd'], list) else [versions['uhd']]
                for m in hd_list:
                    print(f"   HD:  {m}")
                for m in uhd_list:
                    print(f"   UHD: {m}")
                print()
            if not args.hd_path or not args.uhd_path:
                print("   (Run with --hd-path and --uhd-path to see file sizes)")
    else:
        print("\nNo movies found in both HD and UHD lists.")
    print_section("DUPLICATES IN HD LIST")
    if hd_dupes:
        print(f"\nFound {len(hd_dupes)} duplicate groups in HD list:\n")
        if args.hd_path and not args.dry_run:
            hd_del = print_duplicates_with_sizes(hd_dupes, "HD", args.hd_path, "")
            if hd_del:
                to_delete_hd.extend(hd_del)
        elif args.dry_run:
            print_duplicates_dry_run(hd_dupes, "HD", args.hd_path, "")
        else:
            for i, (core, movie_list) in enumerate(sorted(hd_dupes.items()), 1):
                title = core.split('(')[0].strip().title()
                print(f"{i}. {title} ({len(movie_list)} copies)")
                print(f"   Normalized ID: {core}")
                for movie in movie_list:
                    print(f"   - {movie}")
                print()
            if not args.hd_path:
                print("   (Run with --hd-path to see file sizes)")
    else:
        print("\nNo duplicates found in HD list.")
    print_section("DUPLICATES IN UHD LIST")
    if uhd_dupes:
        print(f"\nFound {len(uhd_dupes)} duplicate groups in UHD list:\n")
        if args.uhd_path and not args.dry_run:
            uhd_del = print_duplicates_with_sizes(uhd_dupes, "UHD", "", args.uhd_path)
            if uhd_del:
                to_delete_uhd.extend(uhd_del)
        elif args.dry_run:
            print_duplicates_dry_run(uhd_dupes, "UHD", "", args.uhd_path)
        else:
            for i, (core, movie_list) in enumerate(sorted(uhd_dupes.items()), 1):
                title = core.split('(')[0].strip().title()
                print(f"{i}. {title} ({len(movie_list)} copies)")
                print(f"   Normalized ID: {core}")
                for movie in movie_list:
                    print(f"   - {movie}")
                print()
            if not args.uhd_path:
                print("   (Run with --uhd-path to see file sizes)")
    else:
        print("\nNo duplicates found in UHD list.")
    print_section("SUMMARY")
    print(f"\nMovies in both HD and UHD: {len(cross_dupes)}")
    print(f"Duplicate groups in HD: {len(hd_dupes)}")
    print(f"Duplicate groups in UHD: {len(uhd_dupes)}")
    
    if args.dry_run:
        if args.hd_path and args.uhd_path:
            to_delete_hd_dry = []
            to_delete_uhd_dry = []
            
            # Cross duplicates
            for core, versions in cross_dupes.items():
                hd_list = versions['hd'] if isinstance(versions['hd'], list) else [versions['hd']]
                uhd_list = versions['uhd'] if isinstance(versions['uhd'], list) else [versions['uhd']]
                hd_size = max(get_file_size(args.hd_path, m) for m in hd_list) if hd_list else 0
                uhd_size = max(get_file_size(args.uhd_path, m) for m in uhd_list) if uhd_list else 0
                if hd_size > uhd_size:
                    for m in uhd_list:
                        to_delete_uhd_dry.append((args.uhd_path, m))
                else:
                    for m in hd_list:
                        to_delete_hd_dry.append((args.hd_path, m))
            
            # HD duplicates
            for core, movie_list in hd_dupes.items():
                for movie in movie_list[1:]:
                    to_delete_hd_dry.append((args.hd_path, movie))
            
            # UHD duplicates
            for core, movie_list in uhd_dupes.items():
                for movie in movie_list[1:]:
                    to_delete_uhd_dry.append((args.uhd_path, movie))
            
            total_size = calculate_total_delete_size(to_delete_hd_dry, to_delete_uhd_dry)
            folder_count = len(to_delete_hd_dry) + len(to_delete_uhd_dry)
            if folder_count > 0:
                print(f"\nFolders to be deleted: {folder_count}")
                print(f"Space to be freed: {format_size(total_size)}")
        print("\n[DRY RUN COMPLETE - No changes made]")
    else:
        confirm_and_delete(to_delete_hd, to_delete_uhd)

if __name__ == "__main__":
    main()
