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
    CACHED,
    UNCACHED,
    ERROR,
    STATUSES,
)
from blkcache.ddrescue import iter_filemap_ranges


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


def test_getitem_slice_basic(filemap):
    """Test __getitem__ slice returns transitions with synthetic start/end."""
    filemap[0:25] = STATUS_OK
    filemap[50:75] = STATUS_ERROR

    # Get transitions for beginning section (all OK, no internal transitions)
    result = filemap[0:25]
    assert len(result) == 2
    assert result[0] == (0, NO_SORT, STATUS_OK)  # synthetic start
    assert result[1] == (24, NO_SORT, STATUS_OK)  # synthetic end

    # Get transitions for untried section in middle
    result = filemap[25:50]
    assert len(result) == 2
    assert result[0] == (25, NO_SORT, STATUS_UNTRIED)  # synthetic start
    assert result[1] == (49, NO_SORT, STATUS_UNTRIED)  # synthetic end


def test_getitem_slice_across_boundaries(filemap):
    """Test __getitem__ slice that crosses multiple regions."""
    filemap[20:40] = STATUS_OK
    filemap[60:80] = STATUS_ERROR

    # Get slice that crosses from untried -> ok -> untried -> error -> untried
    result = filemap[10:90]
    assert len(result) == 6
    assert result[0] == (10, NO_SORT, STATUS_UNTRIED)  # synthetic start
    assert result[1] == (20, NO_SORT, STATUS_OK)  # transition to OK
    assert result[2] == (40, NO_SORT, STATUS_UNTRIED)  # transition back to untried
    assert result[3] == (60, NO_SORT, STATUS_ERROR)  # transition to error
    assert result[4] == (80, NO_SORT, STATUS_UNTRIED)  # transition back to untried
    assert result[5] == (89, NO_SORT, STATUS_UNTRIED)  # synthetic end


def test_getitem_slice_single_byte(filemap):
    """Test __getitem__ for single byte ranges."""
    filemap[50:51] = STATUS_ERROR

    result = filemap[49:50]
    assert len(result) == 2
    assert result[0] == (49, NO_SORT, STATUS_UNTRIED)
    assert result[1] == (49, NO_SORT, STATUS_UNTRIED)

    result = filemap[50:51]
    assert len(result) == 2
    assert result[0] == (50, NO_SORT, STATUS_ERROR)
    assert result[1] == (50, NO_SORT, STATUS_ERROR)


def test_getitem_slice_empty_range(filemap):
    """Test __getitem__ for empty range returns empty list."""
    assert filemap[50:50] == []


def test_getitem_slice_bounds_checking(filemap):
    """Test __getitem__ slice bounds checking."""
    # Negative start should raise error
    with pytest.raises(ValueError, match="Negative start index"):
        filemap[-1:50]

    # Stop beyond size should raise error
    with pytest.raises(ValueError, match="Stop index beyond device size"):
        filemap[0:101]


def test_getitem_slice_none_values(filemap):
    """Test __getitem__ slice with None start/stop."""
    filemap[25:75] = STATUS_OK

    # None start defaults to 0
    result = filemap[:25]
    assert len(result) == 2
    assert result[0] == (0, NO_SORT, STATUS_UNTRIED)
    assert result[1] == (24, NO_SORT, STATUS_UNTRIED)

    # None stop defaults to size
    result = filemap[75:]
    assert len(result) == 2
    assert result[0] == (75, NO_SORT, STATUS_UNTRIED)
    assert result[1] == (99, NO_SORT, STATUS_UNTRIED)


def test_getitem_slice_step_not_supported(filemap):
    """Test __getitem__ slice step not supported."""
    with pytest.raises(ValueError, match="Step not supported"):
        filemap[0:50:2]


def test_getitem_single_offset(filemap):
    """Test __getitem__ for single offset."""
    filemap[50] = STATUS_ERROR

    assert filemap[49] == STATUS_UNTRIED
    assert filemap[50] == STATUS_ERROR
    assert filemap[51] == STATUS_UNTRIED


def test_getitem_performance_large_range(filemap):
    """Test __getitem__ efficiently handles large ranges."""
    # Create a large filemap with sparse updates
    large_filemap = FileMap(1000000)  # 1MB
    large_filemap[100000:200000] = STATUS_OK
    large_filemap[500000:600000] = STATUS_ERROR

    # Getting a large range should be efficient (uses bisect)
    result = large_filemap[150000:550000]

    # Should return synthetic start/end plus the transitions in between
    assert len(result) == 4  # start + 200000 transition + 500000 transition + end
    assert result[0] == (150000, NO_SORT, STATUS_OK)  # synthetic start
    assert result[1] == (200000, NO_SORT, STATUS_UNTRIED)  # transition
    assert result[2] == (500000, NO_SORT, STATUS_ERROR)  # transition
    assert result[3] == (549999, NO_SORT, STATUS_ERROR)  # synthetic end


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


def test_helper_sets():
    """Test helper sets for fast status categorization."""
    # Test CACHED set (have data)
    assert STATUS_OK in CACHED
    assert STATUS_SLOW in CACHED
    assert STATUS_SCRAPED in CACHED
    assert STATUS_TRIMMED not in CACHED  # Trimmed = can't get data
    assert STATUS_UNTRIED not in CACHED
    assert STATUS_ERROR not in CACHED

    # Test UNCACHED set (need data)
    assert STATUS_UNTRIED in UNCACHED
    assert STATUS_OK not in UNCACHED
    assert STATUS_ERROR not in UNCACHED

    # Test ERROR set (can't get data)
    assert STATUS_ERROR in ERROR
    assert STATUS_TRIMMED in ERROR  # Trimmed areas are skipped
    assert STATUS_OK not in ERROR
    assert STATUS_UNTRIED not in ERROR

    # Test mutual exclusivity and complete coverage
    all_statuses = {STATUS_OK, STATUS_ERROR, STATUS_UNTRIED, STATUS_TRIMMED, STATUS_SLOW, STATUS_SCRAPED}
    assert CACHED & UNCACHED == set()  # No overlap
    assert CACHED & ERROR == set()  # No overlap
    assert UNCACHED & ERROR == set()  # No overlap
    assert CACHED | UNCACHED | ERROR == all_statuses  # Complete coverage

    # Test STATUSES is the union of all three sets
    assert STATUSES == all_statuses
    assert STATUSES == CACHED | UNCACHED | ERROR


def test_filemap_always_has_end_marker():
    """Test that FileMap always maintains at least 2 transitions (start + end marker)."""
    filemap = FileMap(1024)

    # Initial state should have 2 transitions
    assert len(filemap.transitions) == 2

    # Setting entire range to same status as initial should still keep end marker
    filemap[0:1024] = STATUS_UNTRIED
    assert len(filemap.transitions) == 2

    # Should be able to iterate even after setting everything to same status
    ranges = list(iter_filemap_ranges(filemap))
    assert len(ranges) == 1  # Should have at least one range

    # The end marker should always be present
    assert filemap.transitions[-1][0] == 1024  # End marker at device boundary


def test_edge_marker_boundary_operations():
    """Test operations exactly at device boundary preserve end marker."""
    filemap = FileMap(1024)

    # Set status right up to device boundary - should preserve end marker
    filemap[0:1024] = STATUS_OK
    assert len(filemap.transitions) == 2
    assert filemap.transitions[-1][0] == 1024

    # Properties should still work
    assert filemap.pos == 1024  # Everything tried, pos should be at end
    assert filemap.status == STATUS_OK

    # Should be able to get ranges at boundary
    result = filemap[1020:1024]
    assert len(result) >= 1


def test_properties_robust_after_end_marker_fix():
    """Test that pos/status properties are robust with preserved end markers."""
    filemap = FileMap(512)

    # Set everything to same status - should maintain end marker
    filemap[0:512] = STATUS_ERROR

    # Properties should work correctly
    assert filemap.pos == 512  # At device end since everything is tried
    assert filemap.status == STATUS_ERROR

    # Set partial back to untried
    filemap[100:200] = STATUS_UNTRIED
    assert filemap.pos == 100  # First untried byte
    assert filemap.status == STATUS_ERROR  # Still highest priority


def test_getitem_robust_with_end_marker():
    """Test __getitem__ works correctly with preserved end markers."""
    filemap = FileMap(256)

    # Fill entire device with same status
    filemap[0:256] = STATUS_SLOW

    # Should be able to query any range
    assert filemap[100] == STATUS_SLOW
    assert filemap[0:256] == [(0, NO_SORT, STATUS_SLOW), (255, NO_SORT, STATUS_SLOW)]
    assert filemap[255:256] == [(255, NO_SORT, STATUS_SLOW), (255, NO_SORT, STATUS_SLOW)]
