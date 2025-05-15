"""
nbdkit Python plugin implementing a sparse on-disk cache.
"""

import contextlib
import errno
import fcntl
import os
import struct
from collections import defaultdict
from pathlib import Path

# Linux ioctl constants
BLKGETSIZE64 = 0x80081272  # <linux/fs.h>
BLKSSZGET = 0x1268  # Get block device sector size
CDROM_GET_BLKSIZE = 0x5313  # Get CDROM block size

# Block status codes (ddrescue compatible)
STATUS_OK = "+"  # Successfully read
STATUS_ERROR = "-"  # Read error
STATUS_UNTRIED = "?"  # Not tried yet
STATUS_TRIMMED = "/"  # Trimmed (not tried because of read error)
STATUS_SLOW = "*"  # Non-trimmed, non-scraped (slow reads)
STATUS_SCRAPED = "#"  # Non-trimmed, scraped (slow reads completed)

DEV: Path | None = None
CACHE: Path | None = None
BLOCK = 2048  # Default block size
METADATA = {}
BLOCK_STATUS = defaultdict(lambda: STATUS_UNTRIED)
LOG_FILE = None


def _has_log():
    """Check if a log file exists for the current cache."""
    log_path = CACHE.with_suffix(f"{CACHE.suffix}.log")
    return log_path.exists()


@contextlib.contextmanager
def _open_log_file(mode="r"):
    """
    Simple context manager for opening the rescue log file.
    """
    log_path = CACHE.with_suffix(f"{CACHE.suffix}.log")

    # Check if file exists when reading
    if mode.startswith("r") and not log_path.exists():
        raise FileNotFoundError(f"Log file does not exist: {log_path}")

    try:
        f = open(log_path, mode)
        yield f
    finally:
        f.close()


def _read_log_file(f):
    """
    Read a ddrescue-compatible log file.
    Returns (comments, metadata, ranges) tuple.
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


def _write_log_file(comments, ranges, f, meta=METADATA):
    """
    Write the ddrescue-compatible log file to disk.

    Args:
        comments: List of comment lines
        ranges: List of (start, end, status) tuples
        f: File-like object to write to
        meta: Metadata dictionary (defaults to global METADATA)
    """
    # Write original comments
    for comment in comments:
        f.write(f"{comment}\n")

    # Write our metadata as separate lines
    for key, value in meta.items():
        f.write(f"## blkcache: {key}={value}\n")

    # Write a default header if no comments
    if not comments:
        f.write("# Rescue Logfile. Created by blkcache\n")
        f.write("# current_pos  current_status  current_pass\n")
        f.write(f"0x00000000    {STATUS_UNTRIED}               1\n")
        f.write("#      pos        size  status\n")

    # Write ranges in sorted order
    sorted_ranges = sorted(ranges)
    for start, end, status in sorted_ranges:
        size = end - start + 1
        f.write(f"0x{start:08x}  0x{size:08x}  {status}\n")


def _determine_block_size(device, current_block_size, metadata):
    """
    Determine the appropriate block size to use based on device characteristics and metadata.

    Args:
        device: The device to read block size from
        current_block_size: The current block size setting
        metadata: Metadata dict which may contain block_size or block settings

    Returns:
        Tuple of (block_size, metadata_updates) where:
            block_size: The determined block size to use
            metadata_updates: Dict of metadata values to update
    """
    metadata_updates = {}

    # If block size is already specified, use that
    if "block" in metadata or "block_size" in metadata:
        # Use the block_size from metadata if available
        if "block_size" in metadata:
            block_size = int(metadata["block_size"])
        else:
            # Otherwise keep current block size
            block_size = current_block_size

        metadata_updates["block_size_source"] = "manual"
        return block_size, metadata_updates

    # Otherwise try to auto-detect from device
    try:
        detected_size = _get_sector_size(device)
        metadata_updates["block_size"] = str(detected_size)
        metadata_updates["block_size_source"] = "auto"
        return detected_size, metadata_updates
    except Exception as e:
        # On failure, keep the current block size and record the error
        metadata_updates["block_size_source"] = f"default ({str(e)})"
        return current_block_size, metadata_updates


def _get_sector_size(dev: Path) -> int:
    """Detect the physical sector size of a block device."""
    try:
        with dev.open("rb") as fh:
            # Try BLKSSZGET ioctl (works for most block devices)
            try:
                return struct.unpack("I", fcntl.ioctl(fh, BLKSSZGET, b"\0" * 4))[0]
            except IOError:
                # Try CDROM_GET_BLKSIZE for optical media
                try:
                    return struct.unpack("I", fcntl.ioctl(fh, CDROM_GET_BLKSIZE, b"\0" * 4))[0]
                except IOError:
                    # Default sizes based on device name pattern
                    if "sr" in str(dev) or "cd" in str(dev):
                        return 2048  # Default CD/DVD sector size
                    return 512  # Default for most other devices
    except OSError:
        # Fallback if we can't open the device
        return 512  # Default to 512 bytes (common for hard disks)


def _size(dev: Path) -> int:
    """Get the total size of a device in bytes."""
    try:
        with dev.open("rb") as fh:
            return struct.unpack("Q", fcntl.ioctl(fh, BLKGETSIZE64, b"\0" * 8))[0]
    except OSError:
        return os.stat(dev).st_size


def config(key: str, val: str) -> None:
    """Configure the plugin with parameters passed from nbdkit."""
    global DEV, CACHE, BLOCK, METADATA

    if key == "device":
        DEV = Path(val)
    elif key == "cache":
        CACHE = Path(val)
    elif key == "block":
        BLOCK = int(val)
    elif key == "metadata":
        # Parse metadata string in format "key1=value1,key2=value2"
        for pair in val.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                METADATA[k.strip()] = v.strip()
    else:
        # Store unknown keys in metadata
        METADATA[key] = val


def config_complete() -> None:
    """Validate configuration and set defaults once all config options are received."""
    global DEV, CACHE, BLOCK, METADATA, BLOCK_STATUS

    if DEV is None or CACHE is None:
        raise RuntimeError("device= and cache= are required")

    # Load existing log file if available
    if _has_log():
        with _open_log_file("r") as f:
            comments, log_metadata, ranges = _read_log_file(f)
    else:
        comments = []
        log_metadata = {}
        ranges = []

    # Merge metadata from log file with our current metadata
    # (current settings take precedence)
    for k, v in log_metadata.items():
        if k not in METADATA:
            METADATA[k] = v

    # Determine the appropriate block size
    block_size, metadata_updates = _determine_block_size(device=DEV, current_block_size=BLOCK, metadata=METADATA)

    # Update globals with the results
    BLOCK = block_size
    METADATA.update(metadata_updates)

    # Add default metadata
    if "format_version" not in METADATA:
        METADATA["format_version"] = "1.0"

    # Initialize block status from ranges
    for start, end, status in ranges:
        block_start = start // BLOCK
        block_end = end // BLOCK
        for block_num in range(block_start, block_end + 1):
            BLOCK_STATUS[block_num] = status

    # Write initial log file with merged metadata
    with _open_log_file("w") as f:
        _write_log_file(comments, ranges, f)


def open(_readonly: bool) -> dict[str, int]:
    """Initialize the plugin when nbdkit opens the device."""
    # Get the device size for later use
    device_size = _size(DEV)

    # Add device size to metadata
    METADATA["device_size"] = str(device_size)
    METADATA["block_count"] = str((device_size + BLOCK - 1) // BLOCK)

    return {"size": device_size}


def get_size(h) -> int:
    return h["size"]


def _sector(num: int) -> bytes:
    """
    Get a block-sized chunk of data containing the requested sector.
    Always reads and caches full blocks to ensure data consistency.
    """
    off = num * BLOCK
    # Check if the block is already cached
    with CACHE.open("r+b") as c:
        c.seek(off)
        data = c.read(BLOCK)
        if len(data) > 0 and any(data):
            return data

    # Read from the device
    with DEV.open("rb") as d:
        # Get device size to check if we're at the end
        device_size = _size(DEV)
        d.seek(off)
        data = d.read(BLOCK)

        # No data at all is an error
        if not data:
            raise OSError(errno.EIO, "short read")

        # If it's a partial read but not at end of device, it's an error
        if len(data) < BLOCK and off + len(data) < device_size:
            raise OSError(errno.EIO, f"short read ({len(data)} < {BLOCK})")

    # Write to cache exactly what we read
    with CACHE.open("r+b") as c:
        c.seek(off)
        c.write(data)

    return data


def pread(h, count: int, offset: int) -> bytes:
    first, last = offset // BLOCK, (offset + count - 1) // BLOCK
    blob = b"".join(_sector(i) for i in range(first, last + 1))
    start = offset % BLOCK
    stop = start + count

    return blob[start:stop]
