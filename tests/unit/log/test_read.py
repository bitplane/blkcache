"""Tests for reading ddrescue-compatible log files."""

import io
import pytest

from blkcache.plugin import _read_log_file


@pytest.fixture
def empty_file():
    """Fixture for an empty file."""
    return io.StringIO("")


@pytest.fixture
def comments_only_file():
    """Fixture for a file with only comments."""
    data = (
        "# Rescue Logfile. Created by ddrescue\n"
        "# Command: ddrescue /dev/sr0 image.iso\n"
        "# current_pos  current_status  current_pass\n"
        "0x00000000    ?               1\n"
        "#      pos        size  status\n"
    )
    return io.StringIO(data)


@pytest.fixture
def metadata_file():
    """Fixture for a file with blkcache metadata."""
    data = (
        "# Rescue Logfile. Created by blkcache\n" "## blkcache: block_size=2048\n" "## blkcache: format_version=1.0\n"
    )
    return io.StringIO(data)


@pytest.fixture
def ranges_file():
    """Fixture for a file with data ranges."""
    data = (
        "# Rescue Logfile.\n" "0x00000000  0x00010000  +\n" "0x00010000  0x00001000  -\n" "0x00011000  0x00002000  ?\n"
    )
    return io.StringIO(data)


@pytest.fixture
def complex_file():
    """Fixture for a complex file with comments, metadata, and ranges."""
    data = (
        "# Rescue Logfile. Created by blkcache\n"
        "# current_pos  current_status  current_pass\n"
        "0x00000000    ?               1\n"
        "## blkcache: block_size=2048\n"
        "## blkcache: device_size=104857600\n"
        "#      pos        size  status\n"
        "0x00000000  0x00010000  +\n"
        "0x00010000  0x00001000  -\n"
        "malformed line\n"  # Test handling of malformed lines
        "0x00011000  0x00002000  ?\n"
    )
    return io.StringIO(data)


def test_read_empty_file(empty_file):
    """Test reading an empty log file."""
    comments, metadata, ranges = _read_log_file(empty_file)
    assert comments == []
    assert metadata == {}
    assert ranges == []


def test_read_comments_only(comments_only_file):
    """Test reading a log file with only comments."""
    comments, metadata, ranges = _read_log_file(comments_only_file)
    assert len(comments) == 4
    assert metadata == {}
    assert ranges == []


def test_read_metadata(metadata_file):
    """Test reading a log file with blkcache metadata."""
    comments, metadata, ranges = _read_log_file(metadata_file)
    assert len(comments) == 1
    assert metadata == {"block_size": "2048", "format_version": "1.0"}
    assert ranges == []


def test_read_ranges(ranges_file):
    """Test reading a log file with data ranges."""
    comments, metadata, ranges = _read_log_file(ranges_file)
    assert len(comments) == 1
    assert metadata == {}
    assert len(ranges) == 3

    # Check the first range
    assert ranges[0] == (0x00000000, 0x0000FFFF, "+")
    # Check the second range
    assert ranges[1] == (0x00010000, 0x00010FFF, "-")
    # Check the third range
    assert ranges[2] == (0x00011000, 0x00012FFF, "?")


def test_read_complex_file(complex_file):
    """Test reading a complex log file with comments, metadata, and ranges."""
    comments, metadata, ranges = _read_log_file(complex_file)
    assert len(comments) == 3
    assert metadata == {"block_size": "2048", "device_size": "104857600"}
    assert len(ranges) == 3
