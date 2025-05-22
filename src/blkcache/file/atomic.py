"""
Atomic file writes for frequently-updated or slowly written files.

AtomicFile prevents corruption of small files that are written often,
like ddrescue map files, by writing to "name~" then moving into place.
"""

from pathlib import Path

from .base import File


class AtomicFile(File):
    """File with atomic write operations via temporary files."""

    def __init__(self, path: Path | str, mode: str = "rb"):
        super().__init__(path, mode)
        self._temp_path = None

    @staticmethod
    def check(path: Path) -> bool:
        """Atomic files can handle any regular file path."""
        return not path.is_dir()

    def __enter__(self):
        if "w" in self.mode or "+" in self.mode:
            # For write modes, create temporary file
            self._temp_path = self.path.with_name(f"{self.path.name}~")
            self._f = self._stack.enter_context(self._temp_path.open(self.mode))
        else:
            # For read-only modes, just open normally
            super().__enter__()

        return self

    def __exit__(self, *args):
        result = self._stack.__exit__(*args)

        # Handle atomic replacement on successful write
        if self._temp_path and args[0] is None:
            # Success - move temp file to final location
            self._temp_path.replace(self.path)
        elif self._temp_path and self._temp_path.exists():
            # Error occurred - clean up temp file
            self._temp_path.unlink()

        self._temp_path = None
        return result
