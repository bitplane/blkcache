"""Tests for block size detection functionality."""

from pathlib import Path
from unittest.mock import patch

from blkcache.device import determine_block_size


# Tests for determine_block_size function


def test_explicit_block_param():
    """When 'block' parameter is explicitly set, it should be used without auto-detection."""
    metadata = {"block": "1024"}
    current_block = 2048
    device = Path("/dev/null")

    block_size, updates = determine_block_size(device, current_block, metadata)

    assert block_size == current_block
    assert updates["block_size_source"] == "manual"


def test_explicit_block_size_param():
    """When 'block_size' parameter is explicitly set, it should override the current block size."""
    metadata = {"block_size": "4096"}
    current_block = 2048
    device = Path("/dev/null")

    block_size, updates = determine_block_size(device, current_block, metadata)

    assert block_size == 4096
    assert updates["block_size_source"] == "manual"


@patch("blkcache.device.get_sector_size")
def test_auto_detection_success(mock_get_sector_size):
    """When no parameters are provided, auto-detection should determine the block size."""
    mock_get_sector_size.return_value = 512
    metadata = {}
    current_block = 2048
    device = Path("/dev/null")

    block_size, updates = determine_block_size(device, current_block, metadata)

    assert block_size == 512
    assert updates["block_size"] == "512"
    assert updates["block_size_source"] == "auto"


@patch("blkcache.device.get_sector_size")
def test_auto_detection_failure(mock_get_sector_size):
    """When auto-detection fails, current block size should be kept with error info in metadata."""
    error_msg = "Device not accessible"
    mock_get_sector_size.side_effect = OSError(error_msg)
    metadata = {}
    current_block = 2048
    device = Path("/dev/null")

    block_size, updates = determine_block_size(device, current_block, metadata)

    assert block_size == current_block
    assert "default" in updates["block_size_source"]
    assert error_msg in updates["block_size_source"]



def testdetermine_block_size_with_auto_detect():
    """When auto-detection succeeds, the detected size should be used."""
    # We'll test the higher-level determine_block_size function instead
    # which is more testable without deep mocking
    device = Path("/dev/sda")
    current_block = 2048
    metadata = {}

    # Mock _get_sector_size directly
    with patch("blkcache.device.get_sector_size", return_value=4096):
        block_size, updates = determine_block_size(device, current_block, metadata)

        assert block_size == 4096
        assert updates["block_size"] == "4096"
        assert updates["block_size_source"] == "auto"


def testdetermine_block_size_failure():
    """When auto-detection fails, the current block size should be kept."""
    device = Path("/dev/sda")
    current_block = 2048
    metadata = {}

    # Simulate _get_sector_size throwing an exception
    error_msg = "Device not accessible"
    with patch("blkcache.device.get_sector_size", side_effect=OSError(error_msg)):
        block_size, updates = determine_block_size(device, current_block, metadata)

        # Current block size should be kept
        assert block_size == current_block
        # Error should be recorded in metadata
        assert "default" in updates["block_size_source"]
        assert error_msg in updates["block_size_source"]


def testdetermine_block_size_with_explicit_block():
    """When 'block' parameter is present, auto-detection should be skipped."""
    device = Path("/dev/sda")
    current_block = 2048
    metadata = {"block": "4096"}

    block_size, updates = determine_block_size(device, current_block, metadata)

    assert block_size == current_block  # Current value should be used
    assert updates["block_size_source"] == "manual"


def testdetermine_block_size_with_explicit_block_size():
    """When 'block_size' parameter is present, it should override current value."""
    device = Path("/dev/sda")
    current_block = 2048
    metadata = {"block_size": "4096"}

    block_size, updates = determine_block_size(device, current_block, metadata)

    assert block_size == 4096  # Value from metadata should be used
    assert updates["block_size_source"] == "manual"


def testdetermine_multiple_block_specs():
    """When both 'block' and 'block_size' are present, 'block_size' takes precedence."""
    device = Path("/dev/sda")
    current_block = 1024
    metadata = {"block": "2048", "block_size": "4096"}

    block_size, updates = determine_block_size(device, current_block, metadata)

    assert block_size == 4096  # block_size value should be used
    assert updates["block_size_source"] == "manual"
