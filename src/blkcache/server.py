"""blkcache.server – userspace read-through cache via nbdkit + nbdfuse."""

import contextlib
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from blkcache.file.device import Device
from blkcache.file.removable import Removable


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


def _wait(path: Path, log: logging.Logger, t: float = 10.0, process=None) -> None:
    """Wait for a path to appear, with timeout."""
    end = time.time() + t
    while not path.exists():
        if process and process.poll() is not None:
            raise RuntimeError(f"process exited with code {process.returncode} while waiting for {path}")

        if time.time() > end:
            raise TimeoutError(f"timeout waiting for {path}")

        time.sleep(0.1)
    log.debug("ready: %s", path)


def serve(dev: Path, iso: Path, block: int, keep_cache: bool, log: logging.Logger, shutdown_check=None) -> None:
    if iso.exists() or iso.is_symlink():
        raise FileExistsError(f"refusing to replace existing output path: {iso}")

    with Removable(dev, "rb") as device:
        disc = device.fingerprint()
    cache = _cache_name(iso, disc)
    if not cache.exists():
        with cache.open("wb") as fh, Device(dev, "rb") as device:
            fh.truncate(device.device_size())

    with _workspace(log) as (tmp, mnt):
        sock = tmp / "nbd.sock"

        # Build nbdkit command arguments
        cmd_args = [
            "nbdkit",
            "--foreground",
            "--exit-with-parent",
            "--readonly",
            "--unix",
            str(sock),
            "python",
            str(Path(__file__).with_name("backend.py")),
            f"device={dev}",
            f"cache={cache}",
        ]

        if log.getEffectiveLevel() <= logging.DEBUG:
            cmd_args.insert(1, "-v")

        # Add block size argument only if explicitly specified
        if block is not None:
            cmd_args.append(f"block={block}")

        log.info("Running nbdkit with command: %s", " ".join(cmd_args))

        # Initialize nbdfuse to None to avoid UnboundLocalError
        nbdfuse = None

        nbdkit = subprocess.Popen(cmd_args)

        try:
            _wait(sock, log, process=nbdkit)  # Pass nbdkit to _wait to check for errors
            uri = f"nbd+unix:///?socket={sock}"

            target = mnt / "disc.iso"
            nbdfuse = subprocess.Popen(["nbdfuse", str(target), uri])

            # create dangling symlink immediately
            iso.symlink_to(target)

            _wait(target, log, process=nbdfuse)  # FUSE file materialised, pass nbdfuse to check for errors

            # start media watchdog
            stop_evt = threading.Event()

            def media_change_callback(old_id, new_id):
                if new_id is None:
                    log.info("Media removed")
                else:
                    log.info("Media changed (%s → %s)", old_id, new_id)

            with Removable(dev, "rb") as removable_device:
                threading.Thread(
                    target=removable_device.watch_for_changes, args=(stop_evt, media_change_callback, log), daemon=True
                ).start()

                while not stop_evt.is_set():
                    if shutdown_check and shutdown_check():
                        log.info("Shutdown requested, stopping server...")
                        break
                    time.sleep(0.5)

        finally:
            subprocess.call(["fusermount3", "-u", str(mnt)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if nbdfuse is not None:
                nbdfuse.terminate()
                nbdfuse.wait()
            nbdkit.terminate()
            nbdkit.wait()
            if not keep_cache:
                cache.unlink(missing_ok=True)
                cache.with_name(f"{cache.name}.map").unlink(missing_ok=True)
            if iso.is_symlink() and iso.readlink() == target:
                iso.unlink(missing_ok=True)
