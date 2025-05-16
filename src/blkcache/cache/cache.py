"""
Base class for block device caching implementations.

This module defines the interface that all cache implementations must follow.
"""

from typing import Any, Dict
from ..device import is_rotational


class Cache:
    """
    Base class for caching strategies. Implements nbdkit functions.
    """

    def __init__(self, config: Dict[str, str]):
        """Stores the configuration dictionary for subclasses to use."""
        self.config = config

        # Cache implementations should extract needed parameters from config
        # and store them as instance variables

    def is_rotational(self, handle: Dict[str, Any]) -> bool:
        """Does it spin round, like a CD or an HDD?"""
        return is_rotational(self.device)

    def open(self, readonly: bool = True) -> Dict[str, Any]:
        """Opens required resources and returns a handle with device information."""
        raise NotImplementedError("Subclasses must implement open()")

    def get_size(self, handle: Dict[str, Any]) -> int:
        """Returns the device's total capacity."""
        raise NotImplementedError("Subclasses must implement get_size()")

    def pread(self, handle: Dict[str, Any], count: int, offset: int) -> bytes:
        """Reads data from a specific device location with proper error handling."""
        raise NotImplementedError("Subclasses must implement pread()")

    def close(self, handle: Dict[str, Any]) -> None:
        """Closes connections and flushes pending data. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement close()")

    # Optional capability methods - all return False by default

    def can_write(self, handle: Dict[str, Any]) -> bool:
        """Indicates if write operations are supported."""
        return False

    def can_flush(self, handle: Dict[str, Any]) -> bool:
        """Indicates if this device can flush pending writes to stable storage."""
        return False

    def can_trim(self, handle: Dict[str, Any]) -> bool:
        """Indicates if TRIM/discard operations are supported (SSD optimization)."""
        return False

    def can_zero(self, handle: Dict[str, Any]) -> bool:
        """Indicates if dedicated zeroing operations are supported."""
        return False

    def can_fast_zero(self, handle: Dict[str, Any]) -> bool:
        """Indicates if this device can efficiently zero blocks without writing."""
        return False

    def can_extents(self, handle: Dict[str, Any]) -> bool:
        """Indicates if this device supports extent management operations."""
        return False

    def can_multi_conn(self, handle: Dict[str, Any]) -> bool:
        """Indicates if multiple clients can safely access this device simultaneously."""
        return False

    # Optional operations - raise NotImplementedError by default

    def pwrite(self, handle: Dict[str, Any], buf: bytes, offset: int) -> None:
        """Writes data to a specific device location with proper error handling."""
        raise NotImplementedError("Writing is not supported by this cache implementation")

    def flush(self, handle: Dict[str, Any]) -> None:
        """Forces pending data to be committed to stable storage."""
        raise NotImplementedError("Flushing is not supported by this cache implementation")

    def trim(self, handle: Dict[str, Any], count: int, offset: int) -> None:
        """Advises that a range of blocks are no longer needed (SSD optimization)."""
        raise NotImplementedError("Trimming is not supported by this cache implementation")

    def zero(self, handle: Dict[str, Any], count: int, offset: int) -> None:
        """Efficiently zeros a range of blocks without writing actual zero bytes."""
        raise NotImplementedError("Zeroing is not supported by this cache implementation")

    def extents(self, handle: Dict[str, Any], count: int, offset: int, flags: int) -> Dict[str, Any]:
        """Returns allocation and hole information for the requested block range."""
        raise NotImplementedError("Extents are not supported by this cache implementation")
