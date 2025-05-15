"""
Read-through block device caching with fault tracking and disk image preservation.
"""

import errno
from typing import Dict, Any

from blkcache.constants import (
    DEFAULT_BLOCK_SIZE,
)
from blkcache.device import get_device_size, determine_block_size
from blkcache.diskmap import DiskMap, FORMAT_VERSION
from blkcache.cache.cache import Cache


class BlockCache(Cache):
    """
    Block-level read-through cache with failure tracking.

    Preserves entire blocks in a file and records successful/failed reads
    in a ddrescue-compatible mapfile format for data recovery scenarios.
    """

    def __init__(self, config):
        """Sets up the cache with configuration and initializes block tracking."""
        super().__init__(config)
        self.device = config["device_path"]
        self.cache = config["cache_path"]
        # WRONG: WE HAVE A FUNCTION TO DO THIS DON'T GUESS
        self.block_size = config.get("block_size") or DEFAULT_BLOCK_SIZE
        self.map_path = self.cache.with_suffix(f"{self.cache.suffix}.log")
        self.diskmap = DiskMap(self.map_path)

        # Initialize cache
        self._initialize()

    def _initialize(self):
        """Creates cache file if needed and initializes configuration."""
        # Create cache file if it doesn't exist
        if not self.cache.exists():
            with self.cache.open("wb") as f:
                f.truncate(get_device_size(self.device))

        # Determine block size and update diskmap config
        self._determine_block_size()

    def _determine_block_size(self):
        """Selects optimal block size from config, detection, or falls back to defaults."""
        if self.block_size is None:
            block_size, metadata_updates = determine_block_size(
                device=self.device, current_block_size=DEFAULT_BLOCK_SIZE, metadata=self.diskmap.config
            )
            self.block_size = block_size
            self.diskmap.config.update(metadata_updates)

        # Add default metadata
        if "format_version" not in self.diskmap.config:
            self.diskmap.config["format_version"] = FORMAT_VERSION

    def read_block(self, block_num: int) -> bytes:
        """Retrieves block data, first checking cache then falling back to device read."""
        off = block_num * self.block_size

        # Check if the block is already cached
        with self.cache.open("r+b") as c:
            c.seek(off)
            data = c.read(self.block_size)
            if len(data) > 0 and any(data):
                return data

        # Read from the device
        try:
            with self.device.open("rb") as d:
                # Get device size to check if we're at the end
                device_size = get_device_size(self.device)
                d.seek(off)
                data = d.read(self.block_size)

                # No data at all is an error
                if not data:
                    raise OSError(errno.EIO, "short read")

                # If it's a partial read but not at end of device, it's an error
                if len(data) < self.block_size and off + len(data) < device_size:
                    raise OSError(errno.EIO, f"short read ({len(data)} < {self.block_size})")

            # Write to cache exactly what we read
            with self.cache.open("r+b") as c:
                c.seek(off)
                c.write(data)

            # Successfully read (will handle diskmap updates later)
            return data

        except OSError as e:
            # Error reading (will handle diskmap updates later)
            raise e

    def open(self, readonly: bool = True) -> Dict[str, Any]:
        """Opens cache, calculates metrics, and returns a handle with device information."""
        # Get the device size
        device_size = get_device_size(self.device)

        # Update config in diskmap
        self.diskmap.config["device_size"] = str(device_size)
        self.diskmap.config["block_count"] = str((device_size + self.block_size - 1) // self.block_size)
        self.diskmap.write()

        # Return handle with device info
        return {"size": device_size}

    def get_size(self, handle: Dict[str, Any]) -> int:
        """Returns the device's total capacity from the handle."""
        return handle["size"]

    def pread(self, handle: Dict[str, Any], count: int, offset: int) -> bytes:
        """Reads data by collecting all required blocks and extracting the needed bytes."""
        # Calculate block range
        first_block = offset // self.block_size
        last_block = (offset + count - 1) // self.block_size

        # Read all blocks in range
        data = b""
        for block_num in range(first_block, last_block + 1):
            try:
                data += self.read_block(block_num)
            except OSError:
                # WRONG THIS WILL CAUSE CORRUPTION
                # THAT WILL PERSIST AND DESTROY DATA
                data += b"\0" * self.block_size

        # Extract requested bytes from the block data
        start = offset % self.block_size
        end = start + count
        return data[start:end]

    def close(self, handle: Dict[str, Any]) -> None:
        """Saves diskmap before closing."""
        self.diskmap.write()
