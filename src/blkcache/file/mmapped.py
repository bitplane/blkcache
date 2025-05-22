"""
Memory-mapped file abstraction.

MappedFile uses mmap for efficient access to regular files.
Only works with regular files that support memory mapping.
"""

import mmap
from pathlib import Path

from .base import File


class MMappedFile(File):
    """Memory-mapped file with efficient random access."""

    def __init__(self, path: Path | str, mode: str = "rb"):
        super().__init__(path, mode)
        self._mmap = None

    @staticmethod
    def check(path: Path) -> bool:
        """Check if this is a regular file that can be memory-mapped."""
        try:
            # Must be a regular file (not device, pipe, etc.)
            return path.is_file() and path.stat().st_size > 0
        except (OSError, IOError):
            return False

    def __enter__(self):
        # Open the underlying file first
        self._f = self.path.open(self.mode)

        # Create memory map
        try:
            # Determine mmap access mode
            if "w" in self.mode or "+" in self.mode or "a" in self.mode:
                access = mmap.ACCESS_WRITE
            else:
                access = mmap.ACCESS_READ

            self._mmap = mmap.mmap(self._f.fileno(), 0, access=access)
        except (OSError, ValueError) as e:
            # Close file and raise IOError to hide OS details
            self._f.close()
            raise IOError(f"Cannot memory-map file {self.path}: {e}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._mmap:
            self._mmap.close()
            self._mmap = None
        if self._f:
            self._f.close()
            self._f = None

    def pread(self, count: int, offset: int) -> bytes:
        """Read count bytes at offset using memory map."""
        if self._mmap is None:
            raise IOError("File not opened - use within 'with' statement")

        # Check bounds
        if offset < 0 or offset >= len(self._mmap):
            return b""

        end = min(offset + count, len(self._mmap))
        return self._mmap[offset:end]

    def pwrite(self, data: bytes, offset: int) -> int:
        """Write data at offset using memory map."""
        if self._mmap is None:
            raise IOError("File not opened - use within 'with' statement")

        if self._mmap.access == mmap.ACCESS_READ:
            raise IOError("File opened in read-only mode")

        # Write and let it crash if we go past bounds
        self._mmap[offset : offset + len(data)] = data
        return len(data)

    def size(self) -> int:
        """Get file size from memory map."""
        if self._mmap is None:
            raise IOError("File not opened - use within 'with' statement")
        return len(self._mmap)
