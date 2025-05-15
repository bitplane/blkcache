"""blkcache.server – userspace read-through cache via nbdkit + nbdfuse."""

import contextlib
import fcntl
import hashlib
import logging
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

BLKGETSIZE64 = 0x80081272  # ioctl: get device byte-length


def _device_size(dev: Path) -> int:
    try:
        with dev.open("rb") as fh:
            val = struct.unpack("Q", fcntl.ioctl(fh, BLKGETSIZE64, b"\0" * 8))[0]
            if val:
                return val
    except OSError:
        pass
    sys_sz = Path(f"/sys/class/block/{dev.name}/size")
    return int(sys_sz.read_text()) * 512 if sys_sz.exists() else os.stat(dev).st_size


def _disc_id(dev: Path, head: int = 65_536) -> str:
    with dev.open("rb") as fh:
        return hashlib.sha1(fh.read(head)).hexdigest()[:8]


def _cache_name(out_iso: Path, disc: str) -> Path:
    return out_iso.with_suffix(f"{out_iso.suffix}.cache.{disc}~")


@contextlib.contextmanager
def _workspace(log: logging.Logger):
    tmp = Path(tempfile.mkdtemp(prefix="blkcache_"))
    mnt = tmp / "mnt"
    mnt.mkdir()
    log.debug("workspace %s created", tmp)
    try:
        yield tmp, mnt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        log.debug("workspace %s removed", tmp)


def _wait(path: Path, log: logging.Logger, t: float = 10.0) -> None:
    end = time.time() + t
    while not path.exists():
        if time.time() > end:
            raise TimeoutError(f"timeout waiting for {path}")
        time.sleep(0.1)
    log.debug("ready: %s", path)


def _watch_disc(dev: Path, orig_id: str, orig_mtime: float, stop: threading.Event, log: logging.Logger) -> None:
    """
    Block until the disc is removed or a new one is inserted.
    """
    while not stop.is_set():
        try:
            mtime = dev.stat().st_mtime
            if mtime != orig_mtime:
                try:
                    new_id = _disc_id(dev)
                except OSError as e:
                    if e.errno == 123:  # ENOMEDIUM
                        log.info("tray opened")
                        stop.set()
                        break
                    raise
                if new_id != orig_id:
                    log.info("new disc detected (%s → %s)", orig_id, new_id)
                    stop.set()
                    break
                orig_mtime = mtime
        except FileNotFoundError:
            log.info("device node vanished")
            stop.set()
            break
        time.sleep(1)


def serve(dev: Path, iso: Path, block: int, keep_cache: bool, log: logging.Logger) -> None:
    disc = _disc_id(dev)
    cache = _cache_name(iso, disc)
    if not cache.exists():
        with cache.open("wb") as fh:
            fh.truncate(_device_size(dev))

    with _workspace(log) as (tmp, mnt):
        sock = tmp / "nbd.sock"

        # Build nbdkit command arguments
        cmd_args = [
            "nbdkit",
            "-v",
            "--foreground",
            "--exit-with-parent",
            "--unix",
            str(sock),
            "python",
            str(Path(__file__).with_name("plugin.py")),
            f"device={dev}",
            f"cache={cache}",
        ]

        # Add block size argument only if explicitly specified
        if block is not None:
            cmd_args.append(f"block={block}")

        nbdkit = subprocess.Popen(
            cmd_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            _wait(sock, log)
            uri = f"nbd+unix:///?socket={sock}"

            target = mnt / "disc.iso"
            nbdfuse = subprocess.Popen(
                ["nbdfuse", str(target), uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            # create dangling symlink immediately
            if iso.exists() or iso.is_symlink():
                iso.unlink()
            iso.symlink_to(target)

            _wait(target, log)  # FUSE file materialised

            # start watchdog
            stop_evt = threading.Event()
            threading.Thread(
                target=_watch_disc, args=(dev, disc, dev.stat().st_mtime, stop_evt, log), daemon=True
            ).start()

            while not stop_evt.is_set():
                time.sleep(0.5)

        finally:
            subprocess.call(["fusermount3", "-u", str(mnt)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            nbdfuse.terminate()
            nbdfuse.wait()
            nbdkit.terminate()
            nbdkit.wait()
            if not keep_cache:
                cache.unlink(missing_ok=True)
            if iso.is_symlink():
                iso.unlink(missing_ok=True)
