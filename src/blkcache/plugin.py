"""
nbdkit Python plugin integration for block-level device caching.
"""

from pathlib import Path
from collections import defaultdict

# Import constants using full package name for compatibility with nbdkit and pytest
from blkcache.constants import (
    STATUS_UNTRIED,
    DEFAULT_BLOCK_SIZE,
)

# Import BlockCache class
from blkcache.cache.cache import BlockCache

# Global state
DEV: Path | None = None
CACHE: Path | None = None
BLOCK = DEFAULT_BLOCK_SIZE  # Use constant for default block size
METADATA = {}
BLOCK_STATUS = defaultdict(lambda: STATUS_UNTRIED)

# Cache instance - will be created in config_complete
CACHE_INSTANCE = None


# These functions are now handled by the BlockCache class


def config(key: str, val: str) -> None:
    """Stores device, cache paths and parses metadata key-value pairs."""
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
    """Validates required parameters and initializes the cache implementation."""
    global DEV, CACHE, BLOCK, METADATA, BLOCK_STATUS, CACHE_INSTANCE

    if DEV is None or CACHE is None:
        raise RuntimeError("device= and cache= are required")

    # Create a BlockCache instance
    CACHE_INSTANCE = BlockCache(
        device_path=DEV, cache_path=CACHE, block_size=BLOCK if BLOCK != DEFAULT_BLOCK_SIZE else None
    )

    # The BlockCache initialization will handle:
    # - Loading the mapfile if it exists
    # - Determining the appropriate block size
    # - Creating the cache file if needed

    # Keep using the legacy variables for now to minimize changes
    BLOCK = CACHE_INSTANCE.block_size
    METADATA = CACHE_INSTANCE.metadata
    BLOCK_STATUS = CACHE_INSTANCE.block_status


def open(_readonly: bool) -> dict[str, int]:
    """Creates device handle via the cache implementation."""
    # Use our cache instance to open the device
    return CACHE_INSTANCE.open(_readonly)


def get_size(h) -> int:
    return CACHE_INSTANCE.get_size(h)


def pread(h, count: int, offset: int) -> bytes:
    return CACHE_INSTANCE.pread(h, count, offset)


# Add close function to save the mapfile when closing
def close(h) -> None:
    """Saves mapfile before closing."""
    CACHE_INSTANCE.close(h)


# Optional capability functions - delegate to cache instance
def can_write(h) -> bool:
    return CACHE_INSTANCE.can_write(h)


def can_flush(h) -> bool:
    return CACHE_INSTANCE.can_flush(h)


def can_trim(h) -> bool:
    return CACHE_INSTANCE.can_trim(h)


def can_zero(h) -> bool:
    return CACHE_INSTANCE.can_zero(h)


def can_fast_zero(h) -> bool:
    return CACHE_INSTANCE.can_fast_zero(h)


def can_extents(h) -> bool:
    return CACHE_INSTANCE.can_extents(h)


def is_rotational(h) -> bool:
    return CACHE_INSTANCE.is_rotational(h)


def can_multi_conn(h) -> bool:
    return CACHE_INSTANCE.can_multi_conn(h)
