"""
nbdkit Python backend integration for block-level device caching.

This module serves as the bridge between nbdkit and our file abstraction layer.
It handles the "outside" config (nbdkit parameters) while delegating file
operations to the composed file chain.
"""

import logging
from functools import partial
from pathlib import Path

# Import file detection
from blkcache.file import detect
from blkcache.file.device import DEFAULT_SECTOR_SIZE

log = logging.getLogger(__name__)

# Global state
DEV: Path | None = None
CACHE: Path | None = None
SECTOR_SIZE = DEFAULT_SECTOR_SIZE
METADATA = {}

# Simple dispatch table: handle -> (file_instance, context_generator)
TABLE = {}


def lookup(attr: str, handle: int, table=TABLE):
    """Generic attribute lookup for dispatch."""
    obj, _ = table[handle]
    return getattr(obj, attr)


def open_file_context(path: Path, mode: str):
    """Generator to manage file lifecycle."""
    file_cls = detect(path)
    file_instance = file_cls(path, mode)
    with file_instance as f:
        yield f


def config(key: str, val: str) -> None:
    """Stores device, cache paths and parses metadata key-value pairs."""
    global DEV, CACHE, SECTOR_SIZE, METADATA

    if key == "device":
        DEV = Path(val)
    elif key == "cache":
        CACHE = Path(val)
    elif key == "sector" or key == "block":  # Accept both for compatibility
        SECTOR_SIZE = int(val)
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
    """Validates required parameters."""
    global DEV, CACHE, SECTOR_SIZE, METADATA

    if DEV is None:
        raise RuntimeError("device= is required")

    # For now, just log the config - we'll build file composition later
    log.debug("Config: device=%s, cache=%s, sector_size=%d", DEV, CACHE, SECTOR_SIZE)


def open(_readonly: bool) -> int:
    """Opens device and returns handle ID."""
    mode = "rb" if _readonly else "r+b"
    handle = len(TABLE) + 1
    ctx = open_file_context(DEV, mode)
    obj = next(ctx)
    TABLE[handle] = (obj, ctx)
    log.debug("Opened file %s as handle %d", DEV, handle)
    return handle


def get_size(h: int) -> int:
    """Get file size."""
    obj, _ = TABLE[h]
    return obj.size()


def pread(h: int, count: int, offset: int) -> bytes:
    """Read data at offset."""
    obj, _ = TABLE[h]
    return obj.pread(count, offset)


def close(h: int) -> None:
    """Close file handle."""
    log.debug("Backend close() called for handle %d", h)
    if h in TABLE:
        obj, ctx = TABLE[h]
        try:
            next(ctx)  # Advance generator to trigger cleanup
        except StopIteration:
            pass
        del TABLE[h]
    log.debug("Backend close() completed")


# Optional capability functions - use partial dispatch
can_write = partial(lookup, "can_write")
can_flush = partial(lookup, "can_flush")
can_trim = partial(lookup, "can_trim")
can_zero = partial(lookup, "can_zero")
can_fast_zero = partial(lookup, "can_fast_zero")
can_extents = partial(lookup, "can_extents")
is_rotational = partial(lookup, "is_rotational")
can_multi_conn = partial(lookup, "can_multi_conn")
