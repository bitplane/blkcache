#!/usr/bin/env python3
"""blkcache – CLI entry-point."""

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from . import server


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="blkcache")
    p.add_argument(
        "-b",
        "--block-size",
        type=int,
        default=None,
        help="Block size in bytes (default: auto-detect based on device type)",
    )
    p.add_argument("-k", "--keep-cache", action="store_true", help="keep *.cache.<id>~ after exit")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("device")  # /dev/sr0 …
    p.add_argument("iso")  # symlink clients read
    return p.parse_args(argv)


def _wait_for_disc(dev: Path, log: logging.Logger, shutdown_check=None) -> bool:
    """Block until a disc can be opened for reading. Returns True if disc found, False if shutdown requested."""
    while True:
        if shutdown_check and shutdown_check():
            return False
        try:
            with dev.open("rb"):
                log.debug("media detected in %s", dev)
                return True
        except OSError:
            log.info("no disc in %s — waiting …", dev)
            time.sleep(2)


def main(argv=None) -> None:
    args = _parse(argv)
    # Setup more detailed logging format for debugging
    logging.basicConfig(level=args.log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log = logging.getLogger("blkcache")
    log.info("Starting blkcache with python: %s", sys.executable)

    dev = Path(args.device).resolve()
    iso = Path(args.iso).resolve()

    # Set up graceful shutdown handling
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        log.info("Received signal %d, initiating graceful shutdown...", signum)
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request
    signal.signal(signal.SIGQUIT, signal_handler)  # Ctrl+\
    try:
        signal.signal(signal.SIGHUP, signal_handler)  # Hangup (terminal closed)
    except AttributeError:
        pass  # Not available on all platforms

    try:
        while not shutdown_requested:
            if not _wait_for_disc(dev, log, lambda: shutdown_requested):
                break
            if shutdown_requested:
                break
            server.serve(dev, iso, args.block_size, args.keep_cache, log, lambda: shutdown_requested)
            if not shutdown_requested:
                log.info("waiting for next disc …")
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received, shutting down...")

    log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
