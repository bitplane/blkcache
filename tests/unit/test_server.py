import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from blkcache.server import _wait, serve


def test_wait_reports_child_failure_at_all_log_levels(tmp_path):
    process = Mock()
    process.poll.return_value = 7
    process.returncode = 7

    with pytest.raises(RuntimeError, match="process exited with code 7"):
        _wait(tmp_path / "missing", logging.getLogger("test"), process=process)


def test_serve_refuses_to_replace_existing_output(tmp_path):
    output = tmp_path / "valuable.iso"
    output.write_bytes(b"keep me")

    with pytest.raises(FileExistsError, match="refusing to replace"):
        serve(Path("/dev/does-not-matter"), output, 512, True, logging.getLogger("test"))

    assert output.read_bytes() == b"keep me"
