"""Tests for writing ddrescue-compatible mapfiles."""

import io
import pytest

from blkcache.constants import STATUS_UNTRIED
from blkcache.ddrescue_mapfile import write_mapfile


@pytest.fixture
def output_file():
    """Fixture for a StringIO object to capture output."""
    return io.StringIO()


def test_write_empty_mapfile(output_file):
    """Test writing an empty mapfile."""
    metadata = {"format_version": "1.0", "block_size": "2048"}

    write_mapfile([], [], output_file, metadata)

    result = output_file.getvalue()
    assert "# Rescue Mapfile. Created by blkcache\n" in result
    assert "## blkcache: format_version=1.0\n" in result
    assert "## blkcache: block_size=2048\n" in result
    assert "# current_pos  current_status  current_pass\n" in result
    assert f"0x00000000    {STATUS_UNTRIED}" in result


def test_write_with_comments(output_file):
    """Test writing a mapfile with existing comments."""
    metadata = {"format_version": "1.0", "block_size": "2048"}

    comments = [
        "# Rescue Mapfile. Created by ddrescue version 1.25",
        "# Command: ddrescue /dev/sr0 image.iso rescue.log",
        "# current_pos  current_status  current_pass",
        "0x00000000    ?               1",
        "#      pos        size  status",
    ]

    write_mapfile(comments, [], output_file, metadata)

    result = output_file.getvalue()
    # Check that all comments are preserved
    for comment in comments:
        assert f"{comment}\n" in result
    # Check that metadata is written
    assert "## blkcache: format_version=1.0\n" in result
    assert "## blkcache: block_size=2048\n" in result
    # Default header should not be written since we have comments
    assert result.count("# Rescue Mapfile") == 1


def test_write_with_ranges(output_file):
    """Test writing a mapfile with data ranges."""
    metadata = {"format_version": "1.0", "block_size": "2048"}

    ranges = [
        (0x00010000, 0x00010FFF, "-"),  # Test unsorted order
        (0x00000000, 0x0000FFFF, "+"),
        (0x00011000, 0x00012FFF, "?"),
    ]

    write_mapfile([], ranges, output_file, metadata)

    result = output_file.getvalue()
    # Ranges should be written in sorted order
    assert "0x00000000  0x00010000  +\n" in result
    assert "0x00010000  0x00001000  -\n" in result
    assert "0x00011000  0x00002000  ?\n" in result


def test_write_complex_mapfile(output_file):
    """Test writing a complex mapfile with comments, metadata, and ranges."""
    metadata = {"format_version": "1.0", "block_size": "2048", "device_size": "104857600", "block_count": "51200"}

    comments = [
        "# Rescue Mapfile. Created by blkcache",
        "# current_pos  current_status  current_pass",
        "0x00000000    ?               1",
    ]

    ranges = [(0x00000000, 0x0000FFFF, "+"), (0x00010000, 0x00010FFF, "-"), (0x00011000, 0x00012FFF, "?")]

    write_mapfile(comments, ranges, output_file, metadata)

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
