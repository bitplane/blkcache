"""Tests for writing ddrescue-compatible log files."""

import io
import pytest

from blkcache.plugin import _write_log_file, STATUS_UNTRIED


@pytest.fixture
def output_file():
    """Fixture for a StringIO object to capture output."""
    return io.StringIO()


def test_write_empty_log(output_file):
    """Test writing an empty log file."""
    metadata = {"format_version": "1.0", "block_size": "2048"}

    _write_log_file([], [], output_file, metadata)

    result = output_file.getvalue()
    assert "# Rescue Logfile. Created by blkcache\n" in result
    assert "## blkcache: format_version=1.0\n" in result
    assert "## blkcache: block_size=2048\n" in result
    assert "# current_pos  current_status  current_pass\n" in result
    assert f"0x00000000    {STATUS_UNTRIED}" in result


def test_write_with_comments(output_file):
    """Test writing a log file with existing comments."""
    metadata = {"format_version": "1.0", "block_size": "2048"}

    comments = [
        "# Rescue Logfile. Created by ddrescue version 1.25",
        "# Command: ddrescue /dev/sr0 image.iso rescue.log",
        "# current_pos  current_status  current_pass",
        "0x00000000    ?               1",
        "#      pos        size  status",
    ]

    _write_log_file(comments, [], output_file, metadata)

    result = output_file.getvalue()
    # Check that all comments are preserved
    for comment in comments:
        assert f"{comment}\n" in result
    # Check that metadata is written
    assert "## blkcache: format_version=1.0\n" in result
    assert "## blkcache: block_size=2048\n" in result
    # Default header should not be written since we have comments
    assert result.count("# Rescue Logfile") == 1


def test_write_with_ranges(output_file):
    """Test writing a log file with data ranges."""
    metadata = {"format_version": "1.0", "block_size": "2048"}

    ranges = [
        (0x00010000, 0x00010FFF, "-"),  # Test unsorted order
        (0x00000000, 0x0000FFFF, "+"),
        (0x00011000, 0x00012FFF, "?"),
    ]

    _write_log_file([], ranges, output_file, metadata)

    result = output_file.getvalue()
    # Ranges should be written in sorted order
    assert "0x00000000  0x00010000  +\n" in result
    assert "0x00010000  0x00001000  -\n" in result
    assert "0x00011000  0x00002000  ?\n" in result


def test_write_complex_log(output_file):
    """Test writing a complex log file with comments, metadata, and ranges."""
    metadata = {"format_version": "1.0", "block_size": "2048", "device_size": "104857600", "block_count": "51200"}

    comments = [
        "# Rescue Logfile. Created by blkcache",
        "# current_pos  current_status  current_pass",
        "0x00000000    ?               1",
    ]

    ranges = [(0x00000000, 0x0000FFFF, "+"), (0x00010000, 0x00010FFF, "-"), (0x00011000, 0x00012FFF, "?")]

    _write_log_file(comments, ranges, output_file, metadata)

    result = output_file.getvalue()
    # Check comments
    for comment in comments:
        assert f"{comment}\n" in result
    # Check metadata
    assert "## blkcache: format_version=1.0\n" in result
    assert "## blkcache: block_size=2048\n" in result
    assert "## blkcache: device_size=104857600\n" in result
    assert "## blkcache: block_count=51200\n" in result
    # Check ranges
    assert "0x00000000  0x00010000  +\n" in result
    assert "0x00010000  0x00001000  -\n" in result
    assert "0x00011000  0x00002000  ?\n" in result
