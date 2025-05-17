"""Test the DiskMap transition tracking functionality."""

import pytest
from pathlib import Path
import tempfile
import os

from blkcache.diskmap import DiskMap, STATUS_OK, STATUS_ERROR, STATUS_UNTRIED, STATUS_SLOW, NO_SORT


@pytest.fixture
def diskmap():
    """Create a temporary DiskMap instance."""
    with tempfile.NamedTemporaryFile() as temp:
        # Create a disk map with size 100
        yield DiskMap(Path(temp.name), 100)


def test_initial_state(diskmap):
    """Test the initial state of a new DiskMap."""
    # Should have two transitions: at position 0 and at position 100
    assert len(diskmap.transitions) == 2
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_beginning(diskmap):
    """Test setting status at the beginning of the device."""
    diskmap.set_status(0, 49, STATUS_OK)

    # Should have three transitions now
    assert len(diskmap.transitions) == 3
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (50, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_middle(diskmap):
    """Test setting status in the middle of the device."""
    diskmap.set_status(25, 74, STATUS_OK)

    # Should have four transitions now
    assert len(diskmap.transitions) == 4
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (25, NO_SORT, STATUS_OK)
    assert diskmap.transitions[2] == (75, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_end(diskmap):
    """Test setting status at the end of the device."""
    diskmap.set_status(50, 99, STATUS_OK)

    # Should have three transitions now
    assert len(diskmap.transitions) == 3
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (50, NO_SORT, STATUS_OK)
    assert diskmap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_entire_device(diskmap):
    """Test setting status for the entire device."""
    diskmap.set_status(0, 99, STATUS_OK)

    # Should have two transitions now
    assert len(diskmap.transitions) == 2
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_overlapping(diskmap):
    """Test setting status with overlapping regions."""
    # First set a middle section
    diskmap.set_status(25, 74, STATUS_OK)

    # Then set a section that overlaps both untried sections
    diskmap.set_status(10, 89, STATUS_ERROR)

    # Should have four transitions
    assert len(diskmap.transitions) == 4
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (10, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[2] == (90, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_exact_match(diskmap):
    """Test setting status that exactly matches existing transition points."""
    # Set a middle section
    diskmap.set_status(25, 74, STATUS_OK)

    # Set another section that starts and ends at existing transition points
    diskmap.set_status(25, 74, STATUS_ERROR)

    # Should still have four transitions, but the middle one changed status
    assert len(diskmap.transitions) == 4
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[2] == (75, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_adjacent_regions(diskmap):
    """Test setting status in adjacent regions with the same status."""
    # Set first half
    diskmap.set_status(0, 49, STATUS_OK)

    # Set second half with the same status
    diskmap.set_status(50, 99, STATUS_OK)

    # The transitions should be combined since they have the same status
    assert len(diskmap.transitions) == 2
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_adjacent_different_status(diskmap):
    """Test setting status in adjacent regions with different statuses."""
    # Set first half
    diskmap.set_status(0, 49, STATUS_OK)

    # Set second half with different status
    diskmap.set_status(50, 99, STATUS_ERROR)

    # Should have three transitions with different status
    assert len(diskmap.transitions) == 3
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (50, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_partial_overlap_start(diskmap):
    """Test setting status with partial overlap at the start."""
    # Set initial region
    diskmap.set_status(25, 74, STATUS_OK)

    # Set region that partially overlaps at the start
    diskmap.set_status(10, 40, STATUS_ERROR)

    # Should have five transitions
    assert len(diskmap.transitions) == 5
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (10, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[2] == (41, NO_SORT, STATUS_OK)
    assert diskmap.transitions[3] == (75, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_partial_overlap_end(diskmap):
    """Test setting status with partial overlap at the end."""
    # Set initial region
    diskmap.set_status(25, 74, STATUS_OK)

    # Set region that partially overlaps at the end
    diskmap.set_status(60, 85, STATUS_ERROR)

    # Should have five transitions
    assert len(diskmap.transitions) == 5
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (25, NO_SORT, STATUS_OK)
    assert diskmap.transitions[2] == (60, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[3] == (86, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_contained_region(diskmap):
    """Test setting status for a region completely contained in another."""
    # Set larger region
    diskmap.set_status(20, 79, STATUS_OK)

    # Set smaller region completely contained in the larger one
    diskmap.set_status(40, 59, STATUS_ERROR)

    # Should have six transitions
    assert len(diskmap.transitions) == 6
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[1] == (20, NO_SORT, STATUS_OK)
    assert diskmap.transitions[2] == (40, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[3] == (60, NO_SORT, STATUS_OK)
    assert diskmap.transitions[4] == (80, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[5] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_multiple_updates(diskmap):
    """Test setting status multiple times on the same device."""
    # Set initial state: first quarter is OK
    diskmap.set_status(0, 24, STATUS_OK)
    assert len(diskmap.transitions) == 3
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (25, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)

    # Set second quarter to ERROR
    diskmap.set_status(25, 49, STATUS_ERROR)
    assert len(diskmap.transitions) == 4
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[2] == (50, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)

    # Set third quarter to OK
    diskmap.set_status(50, 74, STATUS_OK)
    assert len(diskmap.transitions) == 5
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[2] == (50, NO_SORT, STATUS_OK)
    assert diskmap.transitions[3] == (75, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)

    # Set fourth quarter to ERROR
    diskmap.set_status(75, 99, STATUS_ERROR)
    assert len(diskmap.transitions) == 5
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert diskmap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[2] == (50, NO_SORT, STATUS_OK)
    assert diskmap.transitions[3] == (75, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_edge_cases(diskmap):
    """Test edge cases for setting status."""
    # Set status for a single block at the start
    diskmap.set_status(0, 0, STATUS_ERROR)
    assert len(diskmap.transitions) == 3
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[1] == (1, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)

    # Set status for a single block at the end
    diskmap.set_status(99, 99, STATUS_OK)
    assert len(diskmap.transitions) == 4
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[1] == (1, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[2] == (99, NO_SORT, STATUS_OK)
    assert diskmap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)

    # Set status for a single block in the middle
    diskmap.set_status(50, 50, STATUS_SLOW)
    assert len(diskmap.transitions) == 6
    assert diskmap.transitions[0] == (0, NO_SORT, STATUS_ERROR)
    assert diskmap.transitions[1] == (1, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[2] == (50, NO_SORT, STATUS_SLOW)
    assert diskmap.transitions[3] == (51, NO_SORT, STATUS_UNTRIED)
    assert diskmap.transitions[4] == (99, NO_SORT, STATUS_OK)
    assert diskmap.transitions[5] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_invalid_input(diskmap):
    """Test handling of invalid inputs to set_status."""
    # Start > end
    with pytest.raises(ValueError):
        diskmap.set_status(50, 25, STATUS_OK)

    # Negative start
    with pytest.raises(ValueError):
        diskmap.set_status(-10, 25, STATUS_OK)

    # End beyond device size
    with pytest.raises(ValueError):
        diskmap.set_status(50, 100, STATUS_OK)


def test_mapfile_read_write():
    """Test reading and writing mapfiles."""
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp_path = Path(temp.name)

        # Create diskmap and set some statuses
        diskmap = DiskMap(temp_path, 100)
        diskmap.set_status(0, 24, STATUS_OK)
        diskmap.set_status(25, 49, STATUS_ERROR)
        diskmap.set_status(50, 74, STATUS_SLOW)

        # Write to file
        diskmap.write()

        # Create new diskmap from same file
        new_diskmap = DiskMap(temp_path, 100)

        # Check that transitions match
        assert len(new_diskmap.transitions) == len(diskmap.transitions)
        for i in range(len(diskmap.transitions)):
            assert new_diskmap.transitions[i][0] == diskmap.transitions[i][0]
            assert new_diskmap.transitions[i][2] == diskmap.transitions[i][2]

    # Clean up
    os.unlink(temp_path)
