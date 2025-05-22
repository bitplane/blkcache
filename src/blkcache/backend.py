"""
nbdkit Python backend integration for block-level device caching.

This module serves as the bridge between nbdkit and our file abstraction layer.
It handles the "outside" config (nbdkit parameters) while delegating file
operations to the composed file chain.
"""

import logging
from pathlib import Path
from typing import Dict, Any

# Import file detection
from blkcache.file import detect
from blkcache.file.device import DEFAULT_SECTOR_SIZE

log = logging.getLogger(__name__)


class HandleManager:
    """Manages file handles and their lifecycle for nbdkit backend."""

    def __init__(self):
        self._handles: Dict[int, Any] = {}  # handle_id -> File instance
        self._next_handle = 1
        self._files = []  # Keep references to context managers

    def open_file(self, path: Path, mode: str) -> int:
        """Open a file and return a handle ID."""
        file_cls = detect(path)
        file_instance = file_cls(path, mode)

        # Enter the context manager and keep reference
        opened_file = file_instance.__enter__()
        self._files.append((file_instance, opened_file))

        # Assign handle and store
        handle = self._next_handle
        self._handles[handle] = opened_file
        self._next_handle += 1

        log.debug("Opened file %s as handle %d", path, handle)
        return handle

    def get_file(self, handle: int):
        """Get the file instance for a handle."""
        if handle not in self._handles:
            raise ValueError(f"Invalid handle: {handle}")
        return self._handles[handle]

    def close_file(self, handle: int) -> None:
        """Close a specific file handle."""
        if handle in self._handles:
            file_instance = self._handles[handle]
            # Find and close the corresponding context manager
            for i, (ctx_mgr, opened_file) in enumerate(self._files):
                if opened_file is file_instance:
                    try:
                        ctx_mgr.__exit__(None, None, None)
                    except Exception as e:
                        log.warning("Error closing file handle %d: %s", handle, e)
                    self._files.pop(i)
                    break

            del self._handles[handle]
            log.debug("Closed handle %d", handle)

    def close_all(self) -> None:
        """Close all open files."""
        for ctx_mgr, _ in self._files:
            try:
                ctx_mgr.__exit__(None, None, None)
            except Exception as e:
                log.warning("Error during cleanup: %s", e)

        self._handles.clear()
        self._files.clear()
        log.debug("Closed all handles")


# Global state
DEV: Path | None = None
CACHE: Path | None = None
SECTOR_SIZE = DEFAULT_SECTOR_SIZE
METADATA = {}

# Handle manager instance
HANDLE_MANAGER = HandleManager()


# These functions are now handled by the BlockCache class


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
    return HANDLE_MANAGER.open_file(DEV, mode)


def get_size(h: int) -> int:
    """Get file size."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return file_instance.size()


def pread(h: int, count: int, offset: int) -> bytes:
    """Read data at offset."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return file_instance.pread(count, offset)


def close(h: int) -> None:
    """Close file handle."""
    log.debug("Backend close() called for handle %d", h)
    HANDLE_MANAGER.close_file(h)
    log.debug("Backend close() completed")


# Optional capability functions - use duck typing
def can_write(h: int) -> bool:
    """Check if file supports writing."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return "w" in file_instance.mode or "a" in file_instance.mode or "+" in file_instance.mode


def can_flush(h: int) -> bool:
    """Check if file supports flushing."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return hasattr(file_instance, "flush")


def can_trim(h: int) -> bool:
    """Check if file supports trim operations."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return hasattr(file_instance, "trim")


def can_zero(h: int) -> bool:
    """Check if file supports zero operations."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return hasattr(file_instance, "zero")


def can_fast_zero(h: int) -> bool:
    """Check if file supports fast zero operations."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return hasattr(file_instance, "fast_zero")


def can_extents(h: int) -> bool:
    """Check if file supports extent operations."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return hasattr(file_instance, "extents")


def is_rotational(h: int) -> bool:
    """Check if underlying storage is rotational."""
    file_instance = HANDLE_MANAGER.get_file(h)
    return hasattr(file_instance, "is_rotational") and file_instance.is_rotational()


def can_multi_conn(h: int) -> bool:
    """Check if file supports multiple connections."""
    # For now, return False for safety
    return False
