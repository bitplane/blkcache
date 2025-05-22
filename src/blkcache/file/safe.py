"""
Safe atomic file writing via memory buffer.

Keeps writes in memory, then atomically writes the whole thing to a temp file
and moves it over the original on close. This prevents partial writes from
corrupting files during crashes, disk full, etc.
"""

import io
import os
from pathlib import Path
from .base import File


class SafeFile(File):
    """File that buffers writes in memory and writes atomically on close."""

    def __init__(self, path: Path | str, mode: str):
        super().__init__(path, mode)
        self._buffer = None
        self._original_mode = mode

    def __enter__(self):
        if "w" in self._original_mode or "a" in self._original_mode or "+" in self._original_mode:
            # For write modes, start with memory buffer
            if "a" in self._original_mode and self.path.exists():
                # Append mode - read existing content first
                with self.path.open("rb") as f:
                    initial_data = f.read()
                self._buffer = io.BytesIO(initial_data)
            else:
                # Write mode - start with empty buffer
                self._buffer = io.BytesIO()
            self._f = self._buffer
        else:
            # Read-only mode - use original file directly
            self._f = self.path.open(self._original_mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            # If we were buffering writes and no exception occurred, write atomically
            if self._buffer and exc_type is None:
                temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp.{os.getpid()}")
                try:
                    with temp_path.open("wb") as temp_file:
                        temp_file.write(self._buffer.getvalue())
                    temp_path.replace(self.path)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise
        finally:
            if self._f:
                self._f.close()
            self._f = None
            self._buffer = None
