#!/usr/bin/env python3
"""blkcache – CLI entry-point."""

import argparse
import logging
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


def _wait_for_disc(dev: Path, log: logging.Logger) -> None:
    """Block until a disc can be opened for reading."""
    while True:
        try:
            with dev.open("rb"):
                log.debug("media detected in %s", dev)
                return
        except OSError:
            log.info("no disc in %s — waiting …", dev)
            time.sleep(2)


def main(argv=None) -> None:
    args = _parse(argv)
    logging.basicConfig(level=args.log_level)
    log = logging.getLogger("blkcache")

    dev = Path(args.device).resolve()
    iso = Path(args.iso).resolve()

    while True:
        _wait_for_disc(dev, log)
        server.serve(dev, iso, args.block_size, args.keep_cache, log)
        log.info("waiting for next disc …")


if __name__ == "__main__":
    main()
