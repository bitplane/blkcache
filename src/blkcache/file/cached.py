"""
Cache file abstraction.

CacheFile wraps another File and provides read-through caching.
Opens the backing file in its __enter__ method.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from .base import File
from .filemap import CACHED, STATUS_ERROR, STATUS_OK, FileMap


class CachedFile(File):
    """Passthrough cache that wraps another File instance."""

    def __init__(
        self,
        backing_file: File,
        cache_file: File,
        filemap: FileMap,
        save_filemap: Callable[[], None] | None = None,
    ):
        # We don't call super().__init__ because we don't have our own path
        self.backing_file = backing_file
        self.cache_file = cache_file
        self.mode = backing_file.mode
        self._f = None  # For compatibility with base File
        self.filemap = filemap
        self.save_filemap = save_filemap
        self._lock = threading.RLock()

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

    @property
    def sector_size(self) -> int:
        """Get sector size from backing file."""
        return self.backing_file.sector_size

    def pread(self, count: int, offset: int) -> bytes:
        """Read valid ranges from the cache and populate misses from the backing file."""
        if count <= 0:
            return b""

        with self._lock:
            end = min(offset + count, self.filemap.size)
            if offset < 0 or offset >= end:
                return b""

            statuses = self.filemap[offset:end]
            runs = []
            run_start = offset
            run_status = statuses[0][2]
            for position, _, status in statuses[1:]:
                if status != run_status:
                    runs.append((run_start, position, run_status))
                    run_start = position
                    run_status = status
            runs.append((run_start, end, run_status))

            result = bytearray()
            for run_start, run_end, status in runs:
                run_size = run_end - run_start
                if status in CACHED:
                    result.extend(self.cache_file.pread(run_size, run_start))
                    continue

                try:
                    data = self.backing_file.pread(run_size, run_start)
                except OSError:
                    self.filemap[run_start:run_end] = STATUS_ERROR
                    self._save_map()
                    raise

                if data:
                    written = self.cache_file.pwrite(data, run_start)
                    if written != len(data):
                        raise OSError(f"short cache write: {written} of {len(data)} bytes")
                    self.cache_file.flush()
                    self.filemap[run_start : run_start + len(data)] = STATUS_OK
                    self._save_map()
                    result.extend(data)

                if len(data) != run_size:
                    break

            return bytes(result)

    def pwrite(self, data: bytes, offset: int) -> int:
        """Write through to both cache and backing file."""
        # Write to backing file first
        with self._lock:
            result = self.backing_file.pwrite(data, offset)
            cached = self.cache_file.pwrite(data[:result], offset)
            if cached != result:
                raise OSError(f"short cache write: {cached} of {result} bytes")
            self.cache_file.flush()
            self.filemap[offset : offset + result] = STATUS_OK
            self._save_map()
            return result

    def _save_map(self) -> None:
        if self.save_filemap is not None:
            self.save_filemap()

    def fingerprint(self, head: int = 65_536) -> str:
        """Get fingerprint from backing file."""
        return self.backing_file.fingerprint(head)

    def __getattr__(self, name):
        """Delegate unknown attributes to backing file."""
        return getattr(self.backing_file, name)
