# Movie Dupecheck

A Python script that finds and removes duplicate movie folders across two movie collections. It detects duplicates within each collection (multiple versions of the same movie) and finds movies that exist in both collections (HD and UHD versions).

## Features

- Detects duplicate movies within a single directory
- Finds movies that exist in both HD and UHD directories
- Compares file sizes to determine which version to keep
- Calculates total space that will be freed
- Dry-run mode to preview what would be deleted
- Handles both folders and files
- Supports various movie naming conventions

## Requirements

- Python 3.6 or higher
- No external dependencies (uses standard library only)

## Usage

Basic usage with directory paths:

```bash
python3 movie_dupecheck.py \
    --hd-file "/path/to/HD/Movies/" \
    --uhd-file "/path/to/UHD/Movies/" \
    --hd-path "/path/to/HD/Movies/" \
    --uhd-path "/path/to/UHD/Movies/"
```

Dry run mode (preview only, no deletion):

```bash
python3 movie_dupecheck.py \
    --hd-file "/path/to/HD/Movies/" \
    --uhd-file "/path/to/UHD/Movies/" \
    --dry-run
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--hd-file` | Path to HD movie list file or directory containing HD movies |
| `--uhd-file` | Path to UHD movie list file or directory containing UHD movies |
| `--hd-path` | Path to HD directory for size checking (optional) |
| `--uhd-path` | Path to UHD directory for size checking (optional) |
| `--dry-run` | Show what would be deleted without actually deleting |
| `--verbose` | Show detailed debug information |

## How It Works

### Duplicate Detection

The script groups movies by extracting the title and year from folder names:

```
Rampage.2018.2160p.UHD.BluRay.x265-TERMiNAL/    ->  Rampage (2018)
Rampage.2018.2160p.UHD.BLURAY.REMUX-EXTREME/    ->  Rampage (2018)
```

Movies with different years are treated as separate entries:

```
Halloween.1978.2160p.UHD.BluRay.x265-TERMiNAL/  ->  Halloween (1978)
Halloween.2018.2160p.UHD.BluRay.x265-TERMiNAL/  ->  Halloween (2018)
```

### What Gets Deleted

Within each duplicate group, the script:
1. Compares file sizes
2. Keeps the largest version
3. Marks smaller versions for deletion

For movies in both HD and UHD directories, it:
1. Compares sizes across both collections
2. Keeps the larger version (typically UHD)
3. Marks the smaller for deletion

### Output

The script shows:
- Total movie counts per collection
- Number of duplicate groups found
- Which folders will be kept vs deleted
- Total space that will be freed
- Prompts for confirmation before deletion

## Example Output

```
================================================================================
 MOVIE DUPLICATE CHECK RESULTS
================================================================================

Total HD movies: 2914
Total UHD movies: 584

================================================================================
 DUPLICATES IN UHD LIST
================================================================================

Found 3 duplicate groups in UHD list:

1. Rampage (3 copies)
     KEEP >    78.54 GB | Rampage.2018.UHD.BLURAY.REMUX-EXTREME/
     DELETE    45.21 GB | Rampage.2018.2160p.UHD.BluRay-TERMiNAL/
     DELETE    32.18 GB | Rampage.2018.2160p.BluRay-PSA/

...

================================================================================
 SUMMARY
================================================================================

Movies in both HD and UHD: 2
Duplicate groups in HD: 5
Duplicate groups in UHD: 6

============================================================
 READY TO DELETE 11 FOLDERS:
 Total space to be freed: 215.43 GB
============================================================

Type 'DELETE' to confirm deletion:
```

## Supported Naming Conventions

The script handles various movie naming formats:

```
Movie.Title.2018.2160p.UHD.BluRay.x265-GROUP/
Movie.Title.(2018).2160p.UHD.BluRay.x265-GROUP/
Movie.Title.2018.MULTi.2160p.UHD.BluRay-GROUP/
Movie.Title.2018.UHD.BLURAY.REMUX-HDR-GROUP/
```

The release group, quality indicators (REMUX, HDR, 10bit, etc.), and audio codecs are preserved in the display output but do not affect duplicate detection.

## Limitations

- Does not detect remakes with the same year (different movies released same year)
- Folder names must contain a year for proper grouping
- Very large collections may take time to scan for file sizes
- SMB/network shares may be slow for size calculations

## License

MIT License
