"""
nbdkit Python plugin implementing a sparse on-disk cache.
"""

import errno
import fcntl
import os
import struct
from pathlib import Path

BLKGETSIZE64 = 0x80081272  # <linux/fs.h>

DEV: Path | None = None
CACHE: Path | None = None
BLOCK = 2048


def _size(dev: Path) -> int:
    try:
        with dev.open("rb") as fh:
            return struct.unpack("Q", fcntl.ioctl(fh, BLKGETSIZE64, b"\0" * 8))[0]
    except OSError:
        return os.stat(dev).st_size


def config(key: str, val: str) -> None:
    global DEV, CACHE, BLOCK
    if key == "device":
        DEV = Path(val)
    elif key == "cache":
        CACHE = Path(val)
    elif key == "block":
        BLOCK = int(val)
    else:
        raise RuntimeError(f"unknown key {key}")


def config_complete() -> None:
    if DEV is None or CACHE is None:
        raise RuntimeError("device= and cache= are required")


def open(_readonly: bool) -> dict[str, int]:
    return {"size": _size(DEV)}


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
