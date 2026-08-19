import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from blkcache.server import _cache_name, _wait, serve


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


def test_serve_preserves_nbdkit_startup_error(monkeypatch, tmp_path):
    device = tmp_path / "device"
    output = tmp_path / "disc.iso"
    removable = MagicMock()
    removable.__enter__.return_value.fingerprint.return_value = "disc-id"
    monkeypatch.setattr("blkcache.server.Removable", Mock(return_value=removable))
    _cache_name(output, "disc-id").write_bytes(b"")

    nbdkit = Mock()
    nbdkit.poll.return_value = 7
    nbdkit.returncode = 7
    monkeypatch.setattr("blkcache.server.subprocess.Popen", Mock(return_value=nbdkit))
    monkeypatch.setattr("blkcache.server.subprocess.call", Mock())

    with pytest.raises(RuntimeError, match="process exited with code 7"):
        serve(device, output, 512, True, logging.getLogger("test"))
