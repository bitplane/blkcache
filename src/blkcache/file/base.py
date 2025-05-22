import hashlib
from pathlib import Path


class File:
    """Base file class with position-independent read/write operations."""

    def __init__(self, path: Path | str, mode: str):
        self.path = Path(path)
        self.mode = mode
        self._f = None

    @staticmethod
    def check(path: Path) -> bool:
        """Check if this class can handle the given path."""
        return path.is_file() or (path.exists() and not path.is_dir())

    def __enter__(self):
        self._f = self.path.open(self.mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._f:
            self._f.close()
        self._f = None

    def __getattr__(self, name):
        """Delegate unknown attributes to the underlying file object."""
        if self._f is None:
            raise ValueError("File not opened - use within 'with' statement")
        return getattr(self._f, name)

    def pread(self, count: int, offset: int) -> bytes:
        """Read count bytes at offset without changing file position."""
        if self._f is None:
            raise ValueError("File not opened - use within 'with' statement")
        current = self._f.tell()
        try:
            self._f.seek(offset)
            return self._f.read(count)
        finally:
            self._f.seek(current)

    def pwrite(self, data: bytes, offset: int) -> int:
        """Write data at offset without changing file position."""
        if self._f is None:
            raise ValueError("File not opened - use within 'with' statement")
        current = self._f.tell()
        try:
            self._f.seek(offset)
            return self._f.write(data)
        finally:
            self._f.seek(current)

    def size(self) -> int:
        """Get file size without changing file position."""
        if self._f is None:
            raise ValueError("File not opened - use within 'with' statement")
        current = self._f.tell()
        try:
            self._f.seek(0, 2)  # Seek to end
            return self._f.tell()
        finally:
            self._f.seek(current)

    def sector_size(self) -> int:
        """Get sector size of the underlying storage device."""
        try:
            # Get the device that contains this file
            stat_result = self.path.stat()
            # For regular files, get the block size from stat
            # This gives us the filesystem's preferred I/O size
            return stat_result.st_blksize
        except (OSError, AttributeError):
            # Fallback to common default
            return 512

    def fingerprint(self, head: int = 65_536) -> str:
        """Generate content fingerprint from file header."""
        return hashlib.sha1(self.pread(head, 0)).hexdigest()[:8]
