"""
Read-through block device caching with fault tracking and disk image preservation.
"""

import errno
from collections import defaultdict
from typing import Dict, Any, List, Tuple, TextIO, Optional

from blkcache.constants import (
    STATUS_UNTRIED,
    DEFAULT_BLOCK_SIZE,
    FORMAT_VERSION,
)
from blkcache.device import get_device_size, determine_block_size
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
        self.metadata = {}
        self.block_status = defaultdict(lambda: STATUS_UNTRIED)
        self.map_path = self.cache.with_suffix(f"{self.cache.suffix}.log")

        # Initialize cache
        self._initialize()

    def _initialize(self):
        """Creates cache file if needed and loads existing block status data."""
        # Create cache file if it doesn't exist
        if not self.cache.exists():
            with self.cache.open("wb") as f:
                f.truncate(get_device_size(self.device))

        # Load mapfile if it exists
        if self.map_path.exists():
            self._load_mapfile()

        # Determine block size
        self._determine_block_size()

    def _load_mapfile(self):
        """Parses mapfile and merges stored block status data with current state."""
        with self.map_path.open("r") as f:
            comments, log_metadata, ranges = self._read_mapfile(f)

        # Merge metadata from log file with our current metadata
        # (current settings take precedence)
        for k, v in log_metadata.items():
            if k not in self.metadata:
                self.metadata[k] = v

        # Initialize block status from ranges
        for start, end, status in ranges:
            block_start = start // self.block_size
            block_end = end // self.block_size
            for block_num in range(block_start, block_end + 1):
                self.block_status[block_num] = status

    def _save_mapfile(self):
        """Persists current block status data in ddrescue-compatible format."""
        # Convert block_status to ranges
        ranges = []

        for block_num, status in self.block_status.items():
            start = block_num * self.block_size
            end = start + self.block_size - 1
            ranges.append((start, end, status))

        # Write mapfile
        with self.map_path.open("w") as f:
            self._write_mapfile([], ranges, f, self.metadata)

    def _determine_block_size(self):
        """Selects optimal block size from config, detection, or falls back to defaults."""
        if self.block_size is None:
            block_size, metadata_updates = determine_block_size(
                device=self.device, current_block_size=DEFAULT_BLOCK_SIZE, metadata=self.metadata
            )
            self.block_size = block_size
            self.metadata.update(metadata_updates)

        # Add default metadata
        if "format_version" not in self.metadata:
            self.metadata["format_version"] = FORMAT_VERSION

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

            # Update block status
            self.block_status[block_num] = "+"  # Successfully read
            return data

        except OSError as e:
            # Mark block as having an error
            self.block_status[block_num] = "-"  # Read error
            raise e

    def open(self, readonly: bool = True) -> Dict[str, Any]:
        """Opens cache, calculates metrics, and returns a handle with device information."""
        # Get the device size
        device_size = get_device_size(self.device)

        # Update metadata
        self.metadata["device_size"] = str(device_size)
        self.metadata["block_count"] = str((device_size + self.block_size - 1) // self.block_size)

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

    def _read_mapfile(self, file: TextIO) -> Tuple[List[str], Dict[str, str], List[Tuple[int, int, str]]]:
        """Reads a ddrescue mapfile and returns comments, metadata, and block ranges."""
        comments = []
        metadata = {}
        ranges = []

        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                # Skip comments and empty lines
                if line.startswith("#"):
                    comments.append(line[1:].strip())
                continue

            if ":" in line:
                # This is metadata
                key, val = line.split(":", 1)
                metadata[key.strip()] = val.strip()
            else:
                # This is a range
                parts = line.split()
                if len(parts) >= 3:
                    start = int(parts[0], 16)
                    length = int(parts[1], 16)
                    status = parts[2]
                    end = start + length - 1
                    ranges.append((start, end, status))

        return comments, metadata, ranges

    def _write_mapfile(
        self,
        comments: List[str],
        ranges: List[Tuple[int, int, str]],
        file: TextIO,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """Writes a ddrescue-compatible mapfile."""
        # Write comments
        for comment in comments:
            file.write(f"# {comment}\n")

        # Write metadata
        if metadata:
            file.write("\n")
            for key, val in sorted(metadata.items()):
                file.write(f"{key}: {val}\n")

        # Write ranges
        if ranges:
            file.write("\n")
            # Sort ranges by start position
            for start, end, status in sorted(ranges, key=lambda x: x[0]):
                length = end - start + 1
                file.write(f"{start:x} {length:x} {status}\n")

    def close(self, handle: Dict[str, Any]) -> None:
        """Saves block status to the mapfile before closing."""
        self._save_mapfile()
