"""Test the DiskMap transition tracking functionality."""

import pytest
from pathlib import Path
import tempfile
import os

from blkcache.diskmap import DiskMap, STATUS_OK, STATUS_ERROR, STATUS_UNTRIED, NO_SORT


class TestDiskMap:
    """Tests for the DiskMap class."""

    @pytest.fixture
    def diskmap(self):
        """Create a temporary DiskMap instance."""
        with tempfile.NamedTemporaryFile() as temp:
            # Create a disk map with size 100
            yield DiskMap(Path(temp.name), 100)

    def test_initial_state(self, diskmap):
        """Test the initial state of a new DiskMap."""
        # Should have two transitions: at position 0 and at position 100
        assert len(diskmap.transitions) == 2
        assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
        assert diskmap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)

    def test_set_status_beginning(self, diskmap):
        """Test setting status at the beginning of the device."""
        diskmap.set_status(0, 49, STATUS_OK)

        # Should have three transitions now
        assert len(diskmap.transitions) == 3
        assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
        assert diskmap.transitions[1] == (50, NO_SORT, STATUS_UNTRIED)
        assert diskmap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)

    def test_set_status_middle(self, diskmap):
        """Test setting status in the middle of the device."""
        diskmap.set_status(25, 74, STATUS_OK)

        # Should have four transitions now
        assert len(diskmap.transitions) == 4
        assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
        assert diskmap.transitions[1] == (25, NO_SORT, STATUS_OK)
        assert diskmap.transitions[2] == (75, NO_SORT, STATUS_UNTRIED)
        assert diskmap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)

    def test_set_status_end(self, diskmap):
        """Test setting status at the end of the device."""
        diskmap.set_status(50, 99, STATUS_OK)

        # Should have three transitions now
        assert len(diskmap.transitions) == 3
        assert diskmap.transitions[0] == (0, NO_SORT, STATUS_UNTRIED)
        assert diskmap.transitions[1] == (50, NO_SORT, STATUS_OK)
        assert diskmap.transitions[2] == (100, NO_SORT, STATUS_UNTRIED)

    def test_set_status_entire_device(self, diskmap):
        """Test setting status for the entire device."""
        diskmap.set_status(0, 99, STATUS_OK)

        # Should have two transitions now
        assert len(diskmap.transitions) == 2
        assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
        assert diskmap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)

    def test_set_status_overlapping(self, diskmap):
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

    def test_set_status_exact_match(self, diskmap):
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

    def test_set_status_adjacent_regions(self, diskmap):
        """Test setting status in adjacent regions."""
        # Set first half
        diskmap.set_status(0, 49, STATUS_OK)

        # Set second half
        diskmap.set_status(50, 99, STATUS_OK)

        # The transitions should be combined since they have the same status
        assert len(diskmap.transitions) == 2
        assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
        assert diskmap.transitions[1] == (100, NO_SORT, STATUS_UNTRIED)

    def test_set_status_complex_sequence(self, diskmap):
        """Test a complex sequence of status settings."""
        # First divide into three equal parts
        diskmap.set_status(0, 32, STATUS_OK)
        diskmap.set_status(33, 65, STATUS_ERROR)
        diskmap.set_status(66, 99, STATUS_OK)

        # Then update the middle of each section
        diskmap.set_status(10, 20, STATUS_UNTRIED)
        diskmap.set_status(40, 50, STATUS_OK)
        diskmap.set_status(75, 85, STATUS_ERROR)

        # Should have 8 transitions
        assert len(diskmap.transitions) == 8
        assert diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
        assert diskmap.transitions[1] == (10, NO_SORT, STATUS_UNTRIED)
        assert diskmap.transitions[2] == (21, NO_SORT, STATUS_OK)
        assert diskmap.transitions[3] == (33, NO_SORT, STATUS_ERROR)
        assert diskmap.transitions[4] == (40, NO_SORT, STATUS_OK)
        assert diskmap.transitions[5] == (51, NO_SORT, STATUS_ERROR)
        assert diskmap.transitions[6] == (66, NO_SORT, STATUS_OK)
        assert diskmap.transitions[7] == (75, NO_SORT, STATUS_ERROR)
        assert diskmap.transitions[8] == (86, NO_SORT, STATUS_OK)
        assert diskmap.transitions[9] == (100, NO_SORT, STATUS_UNTRIED)

    def test_file_loading(self):
        """Test that DiskMap correctly loads saved data."""
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp_path = Path(temp.name)

            # Create and populate a diskmap
            diskmap = DiskMap(temp_path, 100)
            diskmap.set_status(0, 49, STATUS_OK)
            diskmap.set_status(50, 74, STATUS_ERROR)

            # Write it to file
            diskmap.write()

            # Create a new diskmap from the same file
            new_diskmap = DiskMap(temp_path, 100)

            # Verify transitions are loaded correctly
            assert len(new_diskmap.transitions) == 4
            assert new_diskmap.transitions[0] == (0, NO_SORT, STATUS_OK)
            assert new_diskmap.transitions[1] == (50, NO_SORT, STATUS_ERROR)
            assert new_diskmap.transitions[2] == (75, NO_SORT, STATUS_UNTRIED)
            assert new_diskmap.transitions[3] == (100, NO_SORT, STATUS_UNTRIED)

        # Clean up temp file
        os.unlink(temp_path)
