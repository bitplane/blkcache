"""Test the FileMap transition tracking functionality."""

import pytest

from blkcache.file.filemap import (
    FileMap,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_UNTRIED,
    STATUS_SLOW,
    STATUS_TRIMMED,
    STATUS_SCRAPED,
    NO_SORT,
)


@pytest.fixture
def filemap():
    """Create a FileMap instance."""
    return FileMap(100)


def test_initial_state(filemap):
    """Test the initial state of a new FileMap."""
    # Should have two transitions: at position 0 and at position 100
    assert len(filemap.transitions) == 2
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_beginning(filemap):
    """Test setting status at the beginning of the device."""
    filemap[0:50] = STATUS_OK

    # Should have three transitions now
    assert len(filemap.transitions) == 3
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (50, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_middle(filemap):
    """Test setting status in the middle of the device."""
    filemap[25:75] = STATUS_OK

    # Should have four transitions now
    assert len(filemap.transitions) == 4
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (25, NO_SORT, STATUS_OK)
    assert filemap.transitions[2] == (75, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_end(filemap):
    """Test setting status at the end of the device."""
    filemap[50:100] = STATUS_OK

    # Should have three transitions now
    assert len(filemap.transitions) == 3
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (50, NO_SORT, STATUS_OK)
    assert filemap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_entire_device(filemap):
    """Test setting status for the entire device."""
    filemap[0:100] = STATUS_OK

    # Should have two transitions now
    assert len(filemap.transitions) == 2
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_overlapping(filemap):
    """Test setting status with overlapping regions."""
    # First set a middle section
    filemap[25:75] = STATUS_OK

    # Then set a section that overlaps both untried sections
    filemap[10:90] = STATUS_ERROR

    # Should have four transitions
    assert len(filemap.transitions) == 4
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (10, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (90, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_exact_match(filemap):
    """Test setting status that exactly matches existing transition points."""
    # Set a middle section
    filemap[25:75] = STATUS_OK

    # Set another section that starts and ends at existing transition points
    filemap[25:75] = STATUS_ERROR

    # Should still have four transitions, but the middle one changed status
    assert len(filemap.transitions) == 4
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (75, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_adjacent_regions(filemap):
    """Test setting status in adjacent regions with the same status."""
    # Set first half
    filemap[0:50] = STATUS_OK

    # Set second half with the same status
    filemap[50:100] = STATUS_OK

    # The transitions should be combined since they have the same status
    assert len(filemap.transitions) == 2
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_adjacent_different_status(filemap):
    """Test setting status in adjacent regions with different statuses."""
    # Set first half
    filemap[0:50] = STATUS_OK

    # Set second half with different status
    filemap[50:100] = STATUS_ERROR

    # Should have three transitions with different status
    assert len(filemap.transitions) == 3
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (50, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_partial_overlap_start(filemap):
    """Test setting status with partial overlap at the start."""
    # Set initial region
    filemap[25:75] = STATUS_OK

    # Set region that partially overlaps at the start
    filemap[10:41] = STATUS_ERROR

    # Should have five transitions
    assert len(filemap.transitions) == 5
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (10, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (41, NO_SORT, STATUS_OK)
    assert filemap.transitions[3] == (75, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_partial_overlap_end(filemap):
    """Test setting status with partial overlap at the end."""
    # Set initial region
    filemap[25:75] = STATUS_OK

    # Set region that partially overlaps at the end
    filemap[60:86] = STATUS_ERROR

    # Should have five transitions
    assert len(filemap.transitions) == 5
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (25, NO_SORT, STATUS_OK)
    assert filemap.transitions[2] == (60, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[3] == (86, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_contained_region(filemap):
    """Test setting status for a region completely contained in another."""
    # Set larger region
    filemap[20:80] = STATUS_OK

    # Set smaller region completely contained in the larger one
    filemap[40:60] = STATUS_ERROR

    # Should have six transitions
    assert len(filemap.transitions) == 6
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (20, NO_SORT, STATUS_OK)
    assert filemap.transitions[2] == (40, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[3] == (60, NO_SORT, STATUS_OK)
    assert filemap.transitions[4] == (80, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[5] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_multiple_updates(filemap):
    """Test setting status multiple times on the same device."""
    # Set initial state: first quarter is OK
    filemap[0:25] = STATUS_OK
    assert len(filemap.transitions) == 3
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (25, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)

    # Set second quarter to ERROR
    filemap[25:50] = STATUS_ERROR
    assert len(filemap.transitions) == 4
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (50, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)

    # Set third quarter to OK
    filemap[50:75] = STATUS_OK
    assert len(filemap.transitions) == 5
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (50, NO_SORT, STATUS_OK)
    assert filemap.transitions[3] == (75, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)

    # Set fourth quarter to ERROR
    filemap[75:100] = STATUS_ERROR
    assert len(filemap.transitions) == 5
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)
    assert filemap.transitions[1] == (25, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (50, NO_SORT, STATUS_OK)
    assert filemap.transitions[3] == (75, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[4] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_edge_cases(filemap):
    """Test edge cases for setting status."""
    # Set status for a single byte at the start
    filemap[0:1] = STATUS_ERROR
    assert len(filemap.transitions) == 3
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[1] == (1, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)

    # Set status for a single byte at the end
    filemap[99:100] = STATUS_OK
    assert len(filemap.transitions) == 4
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[1] == (1, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[2] == (99, NO_SORT, STATUS_OK)
    assert filemap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)

    # Set status for a single byte in the middle
    filemap[50:51] = STATUS_SLOW
    assert len(filemap.transitions) == 6
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[1] == (1, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[2] == (50, NO_SORT, STATUS_SLOW)
    assert filemap.transitions[3] == (51, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[4] == (99, NO_SORT, STATUS_OK)
    assert filemap.transitions[5] == (100, NO_SORT, STATUS_UNTRIED)


def test_set_status_invalid_input(filemap):
    """Test handling of invalid inputs to slice notation."""
    # End beyond device size
    with pytest.raises(ValueError):
        filemap[50:101] = STATUS_OK

    # Negative start
    with pytest.raises(ValueError):
        filemap[-10:25] = STATUS_OK


def test_slice_bounds_negative_start(filemap):
    """Test that negative start indices raise ValueError."""
    with pytest.raises(ValueError, match="Negative start index"):
        filemap[-1:50] = STATUS_OK


def test_slice_bounds_stop_beyond_size(filemap):
    """Test that stop indices beyond device size raise ValueError."""
    with pytest.raises(ValueError, match="Stop index beyond device size"):
        filemap[0:101] = STATUS_OK


def test_slice_bounds_valid_edge_cases(filemap):
    """Test that valid edge case bounds work correctly."""
    # Start at 0 is valid
    filemap[0:1] = STATUS_OK
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)

    # Stop at exactly device size is valid
    filemap[99:100] = STATUS_ERROR
    assert filemap.transitions[-2][2] == STATUS_ERROR


def test_slice_bounds_none_values(filemap):
    """Test that None start/stop values work correctly."""
    # None start defaults to 0
    filemap[:50] = STATUS_OK
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_OK)

    # None stop defaults to size
    filemap[50:] = STATUS_ERROR
    assert len([t for t in filemap.transitions if t[2] == STATUS_ERROR]) > 0


def test_slice_step_not_supported(filemap):
    """Test that step values other than 1 raise ValueError."""
    with pytest.raises(ValueError, match="Step not supported"):
        filemap[0:50:2] = STATUS_OK


def test_single_offset_assignment(filemap):
    """Test setting status for single offset using filemap[offset] = status."""
    filemap[50] = STATUS_ERROR

    assert len(filemap.transitions) == 4
    assert filemap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[1] == (50, NO_SORT, STATUS_ERROR)
    assert filemap.transitions[2] == (51, NO_SORT, STATUS_UNTRIED)
    assert filemap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)


def test_iterator_basic(filemap):
    """Test iterator yields correct (pos, size, status) tuples."""
    filemap[0:25] = STATUS_OK
    filemap[50:75] = STATUS_ERROR

    ranges = list(filemap)

    assert len(ranges) == 4
    assert ranges[0] == (0, 25, STATUS_OK)
    assert ranges[1] == (25, 25, STATUS_UNTRIED)
    assert ranges[2] == (50, 25, STATUS_ERROR)
    assert ranges[3] == (75, 25, STATUS_UNTRIED)


def test_iterator_empty_transitions():
    """Test iterator handles empty transitions list."""
    filemap = FileMap(100)
    filemap.transitions = []  # Corrupt state

    ranges = list(filemap)
    assert ranges == []


def test_iterator_single_transition():
    """Test iterator with minimal valid transitions."""
    filemap = FileMap(100)
    # Only the end marker - everything untried
    ranges = list(filemap)

    assert len(ranges) == 1
    assert ranges[0] == (0, 100, STATUS_UNTRIED)


def test_pos_property_initial_state(filemap):
    """Test pos property returns 0 when everything is untried."""
    assert filemap.pos == 0


def test_pos_property_partial_completion(filemap):
    """Test pos property returns first untried position."""
    filemap[0:50] = STATUS_OK
    assert filemap.pos == 50

    filemap[50:75] = STATUS_ERROR
    assert filemap.pos == 75


def test_pos_property_fully_complete(filemap):
    """Test pos property returns size when everything is tried."""
    filemap[0:100] = STATUS_OK
    # The end marker is still untried, so pos returns the device size
    assert filemap.pos == 100


def test_pos_property_corrupted_no_untried(filemap):
    """Test pos property raises error when transitions are corrupted."""
    filemap.transitions = [(0, NO_SORT, STATUS_OK), (100, NO_SORT, STATUS_OK)]  # No untried

    with pytest.raises(ValueError, match="FileMap transitions corrupted, someone deleted the end one"):
        filemap.pos


def test_status_property_untried_only(filemap):
    """Test status property with only untried data."""
    assert filemap.status == STATUS_UNTRIED


def test_status_property_mixed_statuses(filemap):
    """Test status property returns highest priority status."""
    filemap[0:25] = STATUS_OK
    filemap[25:50] = STATUS_SLOW
    assert filemap.status == STATUS_UNTRIED  # Highest priority present

    filemap[50:75] = STATUS_ERROR
    assert filemap.status == STATUS_ERROR  # Error has highest priority


def test_status_property_all_priorities(filemap):
    """Test status property with all status types."""
    filemap[0:10] = STATUS_OK
    filemap[10:20] = STATUS_SCRAPED
    filemap[20:30] = STATUS_SLOW
    filemap[30:40] = STATUS_TRIMMED
    filemap[40:50] = STATUS_ERROR
    # 50:100 remains STATUS_UNTRIED

    assert filemap.status == STATUS_ERROR  # Highest priority


def test_status_property_corrupted_insufficient_transitions():
    """Test status property raises error with insufficient transitions."""
    filemap = FileMap(100)
    filemap.transitions = [(0, NO_SORT, STATUS_OK)]  # Missing end marker

    with pytest.raises(ValueError, match="insufficient entries"):
        filemap.status


def test_status_property_corrupted_no_valid_statuses():
    """Test status property raises error when no valid statuses found."""
    filemap = FileMap(100)
    # Corrupt the transitions to have invalid status
    filemap.transitions = [(0, NO_SORT, "INVALID"), (100, NO_SORT, "INVALID")]

    with pytest.raises(ValueError, match="no valid statuses found"):
        filemap.status
