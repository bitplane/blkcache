"""
Cache file abstraction.

CacheFile wraps another File and provides read-through caching.
Opens the backing file in its __enter__ method.
"""

from pathlib import Path

from .base import File


class CacheFile(File):
    """Passthrough cache that wraps another File instance."""

    def __init__(self, backing_file: File, cache_file: File):
        # We don't call super().__init__ because we don't have our own path
        self.backing_file = backing_file
        self.cache_file = cache_file
        self.mode = backing_file.mode
        self._f = None  # For compatibility with base File

    @staticmethod
    def check(path: Path) -> bool:
        """CacheFile doesn't check paths - it's a wrapper."""
        return False  # Never auto-detected, always explicit

    @property
    def path(self) -> Path:
        """Return the backing file's path."""
        return self.backing_file.path

    def __enter__(self):
        # Open both backing and cache files
        self.backing_file = self.backing_file.__enter__()
        self.cache_file = self.cache_file.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Close both files
        try:
            if self.cache_file:
                self.cache_file.__exit__(exc_type, exc_val, exc_tb)
        finally:
            if self.backing_file:
                self.backing_file.__exit__(exc_type, exc_val, exc_tb)

    def size(self) -> int:
        """Get size from backing file."""
        return self.backing_file.size()

    def sector_size(self) -> int:
        """Get sector size from backing file."""
        return self.backing_file.sector_size()

    def pread(self, count: int, offset: int) -> bytes:
        """Read with cache - try cache first, then backing file."""
        try:
            # Try reading from cache first
            data = self.cache_file.pread(count, offset)
            if len(data) == count:
                return data
        except (IOError, OSError):
            pass  # Cache miss or error, fall through to backing file

        # Read from backing file
        data = self.backing_file.pread(count, offset)

        # Update cache
        self.cache_file.pwrite(data, offset)

        return data

    def pwrite(self, data: bytes, offset: int) -> int:
        """Write through to both cache and backing file."""
        # Write to backing file first
        result = self.backing_file.pwrite(data, offset)

        # Update cache
        self.cache_file.pwrite(data, offset)

        return result

    def fingerprint(self, head: int = 65_536) -> str:
        """Get fingerprint from backing file."""
        return self.backing_file.fingerprint(head)

    def __getattr__(self, name):
        """Delegate unknown attributes to backing file."""
        return getattr(self.backing_file, name)
