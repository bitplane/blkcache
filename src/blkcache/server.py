"""blkcache.server – userspace read-through cache via nbdkit + nbdfuse."""

import contextlib
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from blkcache.device import get_device_size
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
        # Check process status if available and debugging
        if process and log.getEffectiveLevel() <= logging.DEBUG:
            if process.poll() is not None:
                log.debug("Process exited with code: %d", process.returncode)
                if hasattr(process, "stderr") and hasattr(process, "stdout"):
                    stderr = process.stderr.read() if process.stderr else ""
                    stdout = process.stdout.read() if process.stdout else ""
                    log.debug("Process stderr: %s", stderr)
                    log.debug("Process stdout: %s", stdout)
                break

        if time.time() > end:
            # If we're timing out and have debug enabled, get process output
            if process and log.getEffectiveLevel() <= logging.DEBUG:
                if hasattr(process, "stderr") and hasattr(process, "stdout"):
                    stderr = process.stderr.read() if process.stderr else ""
                    stdout = process.stdout.read() if process.stdout else ""
                    log.debug("Process stderr on timeout: %s", stderr)
                    log.debug("Process stdout on timeout: %s", stdout)
            raise TimeoutError(f"timeout waiting for {path}")

        time.sleep(0.1)
    log.debug("ready: %s", path)


def serve(dev: Path, iso: Path, block: int, keep_cache: bool, log: logging.Logger, shutdown_check=None) -> None:
    with Removable(dev, "rb") as device:
        disc = device.fingerprint()
    cache = _cache_name(iso, disc)
    if not cache.exists():
        with cache.open("wb") as fh:
            fh.truncate(get_device_size(dev))

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
            str(Path(__file__).with_name("backend.py")),
            f"device={dev}",
            f"cache={cache}",
        ]

        # Add block size argument only if explicitly specified
        if block is not None:
            cmd_args.append(f"block={block}")

        log.info("Running nbdkit with command: %s", " ".join(cmd_args))

        # Initialize nbdfuse to None to avoid UnboundLocalError
        nbdfuse = None

        # For DEBUG level, capture output; otherwise suppress it
        if log.getEffectiveLevel() <= logging.DEBUG:
            nbdkit = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # Get strings back instead of bytes
            )
        else:
            nbdkit = subprocess.Popen(
                cmd_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        try:
            _wait(sock, log, process=nbdkit)  # Pass nbdkit to _wait to check for errors
            uri = f"nbd+unix:///?socket={sock}"

            target = mnt / "disc.iso"
            # Capture nbdfuse output for debugging
            if log.getEffectiveLevel() <= logging.DEBUG:
                nbdfuse = subprocess.Popen(
                    ["nbdfuse", str(target), uri], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
            else:
                nbdfuse = subprocess.Popen(
                    ["nbdfuse", str(target), uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

            # create dangling symlink immediately
            if iso.exists() or iso.is_symlink():
                iso.unlink()
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
            # Ensure diskmap is written before shutdown
            try:
                from blkcache.cache.through import BlockCache

                config = {"device_path": dev, "cache_path": cache}
                cache_instance = BlockCache(config)
                cache_instance.diskmap.write()
                log.debug("Diskmap written on shutdown")
            except Exception as e:
                log.warning("Failed to write diskmap on shutdown: %s", e)

            subprocess.call(["fusermount3", "-u", str(mnt)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if nbdfuse is not None:
                nbdfuse.terminate()
                nbdfuse.wait()
            nbdkit.terminate()
            nbdkit.wait()
            if not keep_cache:
                cache.unlink(missing_ok=True)
            if iso.is_symlink():
                iso.unlink(missing_ok=True)
