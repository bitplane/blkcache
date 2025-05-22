"""
Removable device abstraction with media change detection.

Removable class extends Device with functionality for optical drives,
USB drives, and other removable media that can be ejected or changed.
"""

import fcntl
import logging
import struct
import threading
import time
from functools import lru_cache
from pathlib import Path

from .device import Device, BLKSSZGET, DEFAULT_SECTOR_SIZE

# Linux ioctl constants for removable media
CDROM_GET_BLKSIZE = 0x5313  # Get CDROM block size

# Default sector size for optical media
DEFAULT_CDROM_SECTOR_SIZE = 2048


class Removable(Device):
    """Removable device with media change detection."""

    def __init__(self, path: Path | str, mode: str = "rb"):
        super().__init__(path, mode)
        # Optical drives and floppy disks are rotational
        self.is_rotational = self._is_optical() or self._is_floppy()

    def _is_optical(self) -> bool:
        """Check if this is an optical drive (CD/DVD)."""
        device_name = self.path.name
        return device_name.startswith(("sr", "scd")) or "cdrom" in str(self.path)

    def _is_floppy(self) -> bool:
        """Check if this is a floppy disk drive."""
        device_name = self.path.name
        # fd0, fd1 for traditional floppies, sd* devices need more checking
        if device_name.startswith("fd"):
            return True

        # Check for USB floppies via sysfs
        try:
            model_path = Path(f"/sys/block/{device_name}/device/model")
            if model_path.exists():
                model = model_path.read_text().strip().lower()
                return "floppy" in model or "fd" in model
        except Exception:
            pass

        return False

    @staticmethod
    def check(path: Path) -> bool:
        """Check if this is a removable block device."""
        if not path.is_block_device():
            return False

        # Check /sys/block for removable flag
        removable_path = Path(f"/sys/block/{path.name}/removable")
        if removable_path.exists():
            try:
                return removable_path.read_text().strip() == "1"
            except (OSError, IOError):
                pass

        p = str(path)
        return p.startswith("/dev/") and ("sr" in p or "cd" in p)

    @property
    @lru_cache(maxsize=1)
    def sector_size(self) -> int:
        """Get sector size with CDROM-specific ioctl support."""
        try:
            # Try standard block device ioctl first
            return struct.unpack("I", fcntl.ioctl(self._f, BLKSSZGET, b"\0" * 4))[0]
        except (OSError, IOError):
            try:
                # Try CDROM_GET_BLKSIZE for optical media
                return struct.unpack("I", fcntl.ioctl(self._f, CDROM_GET_BLKSIZE, b"\0" * 4))[0]
            except (OSError, IOError):
                # Default for optical media based on device name
                if "sr" in str(self.path) or "cd" in str(self.path):
                    return DEFAULT_CDROM_SECTOR_SIZE
                return DEFAULT_SECTOR_SIZE

    def watch_for_changes(self, stop_event: threading.Event, callback=None, logger=None) -> None:
        """
        Monitor device for media changes.

        Args:
            stop_event: Threading event to signal when to stop monitoring
            callback: Function to call on media change (old_id, new_id)
            logger: Logger for debug messages
        """
        if logger is None:
            logger = logging.getLogger(__name__)

        try:
            orig_id = self.fingerprint()
            orig_mtime = self.path.stat().st_mtime
        except (OSError, IOError) as e:
            logger.warning("Cannot initialize media watch: %s", e)
            return

        logger.debug("Starting media watch for %s (id: %s)", self.path, orig_id)

        while not stop_event.is_set():
            try:
                mtime = self.path.stat().st_mtime
                if mtime != orig_mtime:
                    try:
                        new_id = self.fingerprint()
                    except OSError as e:
                        if e.errno == 123:  # ENOMEDIUM
                            logger.info("Media removed from %s", self.path)
                            if callback:
                                callback(orig_id, None)
                            stop_event.set()
                            break
                        raise

                    if new_id != orig_id:
                        logger.info("Media changed in %s (%s → %s)", self.path, orig_id, new_id)
                        if callback:
                            callback(orig_id, new_id)
                        stop_event.set()
                        break
                    orig_mtime = mtime

            except FileNotFoundError:
                logger.info("Device %s disappeared", self.path)
                if callback:
                    callback(orig_id, None)
                stop_event.set()
                break

            time.sleep(1)

        logger.debug("Media watch stopped for %s", self.path)
