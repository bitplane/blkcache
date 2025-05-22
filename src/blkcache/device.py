"""
Utility functions for device operations.

This module provides functions for interacting with block devices,
such as getting the device size, detecting rotational status, etc.
"""

import fcntl
import os
import struct
from pathlib import Path
from typing import Optional, Tuple

from blkcache.constants import BLKGETSIZE64, BLKSSZGET, CDROM_GET_BLKSIZE, DEFAULT_BLOCK_SIZE


def get_device_size(dev_path: Path) -> int:
    """Determines a block device's total capacity in bytes using multiple fallback methods."""
    try:
        with dev_path.open("rb") as fh:
            val = struct.unpack("Q", fcntl.ioctl(fh, BLKGETSIZE64, b"\0" * 8))[0]
            if val:
                return val
    except OSError:
        pass

    # Try alternate methods
    sys_sz = Path(f"/sys/class/block/{dev_path.name}/size")
    if sys_sz.exists():
        return int(sys_sz.read_text()) * 512

    # Fall back to stat
    return os.stat(dev_path).st_size


def get_sector_size(dev_path: Path) -> int:
    """Determines sector size: from block device ioctls, existing .log file, or 512B default."""
    # 1. If it's a block device, get the actual sector size
    if dev_path.is_block_device():
        try:
            with dev_path.open("rb") as fh:
                # Try BLKSSZGET ioctl (works for most block devices)
                try:
                    return struct.unpack("I", fcntl.ioctl(fh, BLKSSZGET, b"\0" * 4))[0]
                except IOError:
                    # Try CDROM_GET_BLKSIZE for optical media
                    try:
                        return struct.unpack("I", fcntl.ioctl(fh, CDROM_GET_BLKSIZE, b"\0" * 4))[0]
                    except IOError:
                        # Default sizes based on device name pattern
                        if "sr" in str(dev_path) or "cd" in str(dev_path):
                            return DEFAULT_BLOCK_SIZE  # Default CD/DVD sector size
                        return 512  # Default for most other devices
        except OSError:
            return 512  # Fallback if we can't open the device

    # 2. If it's a regular file, check for existing .log file
    log_path = dev_path.with_suffix(f"{dev_path.suffix}.log")
    if log_path.exists():
        try:
            from blkcache.diskmap import DiskMap

            # Get file size for DiskMap validation
            file_size = get_device_size(dev_path)
            temp_diskmap = DiskMap(log_path, file_size)
            if "block_size" in temp_diskmap.config:
                return int(temp_diskmap.config["block_size"])
        except (ValueError, KeyError, Exception):
            pass  # Fall through to default

    # 3. Default to 512 bytes for regular files
    return 512


def is_rotational(dev_path: Path) -> bool:
    """Determines if the storage medium spins (like HDDs or optical media) or uses flash (SSD)."""
    try:
        # Check sys path for rotational status
        rotational_path = Path(f"/sys/block/{dev_path.name}/queue/rotational")
        if rotational_path.exists():
            return rotational_path.read_text().strip() == "1"

        # Heuristic: CDs and DVDs are rotational
        if "sr" in str(dev_path) or "cd" in str(dev_path):
            return True

        # Default: assume non-rotational for modern devices
        return False
    except Exception:
        # Default: assume non-rotational for modern devices
        return False


def determine_block_size(
    device: Path, current_block_size: int = DEFAULT_BLOCK_SIZE, metadata: Optional[dict] = None
) -> Tuple[int, dict]:
    """
    Selects optimal block size from either explicit config, device detection, or defaults.
    Returns both the block size and metadata updates to record the decision.
    """
    metadata = metadata or {}
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
        detected_size = get_sector_size(device)
        metadata_updates["block_size"] = str(detected_size)
        metadata_updates["block_size_source"] = "auto"
        return detected_size, metadata_updates
    except Exception as e:
        # On failure, keep the current block size and record the error
        metadata_updates["block_size_source"] = f"default ({str(e)})"
        return current_block_size, metadata_updates
