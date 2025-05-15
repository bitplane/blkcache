"""
Utilities for handling ddrescue-compatible mapfiles.
"""

import contextlib
from pathlib import Path
from typing import List, Tuple, Dict, Iterator, TextIO, Optional

from blkcache.constants import STATUS_UNTRIED


@contextlib.contextmanager
def open_mapfile(log_path: Path, mode: str = "r") -> Iterator[TextIO]:
    """
    Context manager for opening a ddrescue mapfile.

    Args:
        log_path: Path to the mapfile
        mode: File open mode ('r' for read, 'w' for write, 'a' for append)

    Raises:
        FileNotFoundError: If file doesn't exist when reading

    Yields:
        An open file handle
    """
    # Check if file exists when reading
    if mode.startswith("r") and not log_path.exists():
        raise FileNotFoundError(f"Mapfile does not exist: {log_path}")

    f = None
    try:
        # Use Path.open() method for consistent file handling
        # Ensure we're using text mode
        full_mode = mode + "t" if "t" not in mode and "b" not in mode else mode
        f = log_path.open(mode=full_mode)
        yield f
    finally:
        if f is not None:
            f.close()


def read_mapfile(f: TextIO) -> Tuple[List[str], Dict[str, str], List[Tuple[int, int, str]]]:
    """
    Read a ddrescue-compatible mapfile.

    Args:
        f: Open file handle to read from

    Returns:
        Tuple of (comments, metadata, ranges):
            comments: List of comment lines
            metadata: Dictionary of metadata key-value pairs
            ranges: List of (start, end, status) tuples
    """
    comments = []
    ranges = []
    metadata = {}

    for line in f:
        line = line.rstrip("\n")

        # Process comments
        if line.startswith("#"):
            # Extract our metadata
            if line.startswith("## blkcache:"):
                meta_str = line[12:].strip()
                if "=" in meta_str:
                    k, v = meta_str.split("=", 1)
                    metadata[k.strip()] = v.strip()
            else:
                comments.append(line)
            continue

        # Parse data lines: pos size status
        parts = line.strip().split()
        if len(parts) >= 3:
            try:
                start = int(parts[0], 16)
                size = int(parts[1], 16)
                status = parts[2]
                end = start + size - 1
                ranges.append((start, end, status))
            except ValueError:
                # Skip malformed lines
                pass

    return comments, metadata, ranges


def write_mapfile(
    comments: List[str], ranges: List[Tuple[int, int, str]], f: TextIO, meta: Optional[Dict[str, str]] = None
) -> None:
    """
    Write a ddrescue-compatible mapfile.

    Args:
        comments: List of comment lines
        ranges: List of (start, end, status) tuples
        f: File-like object to write to
        meta: Metadata dictionary (optional)
    """
    # Use empty dict if meta is None
    meta = meta or {}

    # Write original comments
    for comment in comments:
        f.write(f"{comment}\n")

    # Write our metadata as separate lines
    for key, value in meta.items():
        f.write(f"## blkcache: {key}={value}\n")

    # Write a default header if no comments
    if not comments:
        f.write("# Rescue Mapfile. Created by blkcache\n")
        f.write("# current_pos  current_status  current_pass\n")
        f.write(f"0x00000000    {STATUS_UNTRIED}               1\n")
        f.write("#      pos        size  status\n")

    # Write ranges in sorted order
    sorted_ranges = sorted(ranges)
    for start, end, status in sorted_ranges:
        size = end - start + 1
        f.write(f"0x{start:08x}  0x{size:08x}  {status}\n")
