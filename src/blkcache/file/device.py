"""
Device file abstraction with ioctl support.

Device class that extends File with block device operations like
sector size detection, device sizing, and rotational status.
"""

import fcntl
import struct
from functools import lru_cache
from pathlib import Path

from .base import File

# Linux ioctl constants
BLKGETSIZE64 = 0x80081272  # <linux/fs.h> Get device byte-length
BLKSSZGET = 0x1268  # Get block device sector size

# Default sector size
DEFAULT_SECTOR_SIZE = 512


class Device(File):
    """Device file with block device operations."""

    def __init__(self, path: Path | str, mode: str = "rb"):
        super().__init__(path, mode)
        # Update capability based on device type
        self.is_rotational = self._check_rotational()

    @staticmethod
    def check(path: Path) -> bool:
        """Check if this is a block device."""
        return path.is_block_device()

    def device_size(self) -> int:
        """Get device capacity in bytes using ioctl or fallback methods."""
        try:
            # Try block device ioctl first
            val = struct.unpack("Q", fcntl.ioctl(self._f, BLKGETSIZE64, b"\0" * 8))[0]
            if val:
                return val
        except OSError:
            pass

        # Try alternate methods
        sys_sz = Path(f"/sys/class/block/{self.path.name}/size")
        if sys_sz.exists():
            return int(sys_sz.read_text()) * 512

        # Fall back to file size
        return self.size()

    @property
    @lru_cache(maxsize=1)
    def sector_size(self) -> int:
        """Get device sector size using ioctl."""
        try:
            # Try BLKSSZGET ioctl (works for most block devices)
            return struct.unpack("I", fcntl.ioctl(self._f, BLKSSZGET, b"\0" * 4))[0]
        except (OSError, IOError):
            return DEFAULT_SECTOR_SIZE

    def _check_rotational(self) -> bool:
        """Check if device uses spinning media (HDD) vs flash (SSD)."""
        try:
            # Check sys path for rotational status
            rotational_path = Path(f"/sys/block/{self.path.name}/queue/rotational")
            if rotational_path.exists():
                return rotational_path.read_text().strip() == "1"

            # Default: assume non-rotational for modern devices
            return False
        except Exception:
            # Default: assume non-rotational for modern devices
            return False
