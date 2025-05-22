"""Test the ddrescue module functionality."""

import pytest
from io import StringIO

from blkcache.ddrescue import iter_filemap_ranges, parse_status, load, save
from blkcache.file.filemap import (
    FileMap,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_UNTRIED,
    STATUS_SLOW,
    STATUS_TRIMMED,
    STATUS_SCRAPED,
    STATUSES,
)


@pytest.fixture
def filemap():
    """Create a FileMap instance."""
    return FileMap(100)


def test_iter_filemap_ranges_basic(filemap):
    """Test iter_filemap_ranges yields correct (pos, size, status) tuples."""
    filemap[0:25] = STATUS_OK
    filemap[50:75] = STATUS_ERROR

    ranges = list(iter_filemap_ranges(filemap))

    assert len(ranges) == 4
    assert ranges[0] == (0, 25, STATUS_OK)
    assert ranges[1] == (25, 25, STATUS_UNTRIED)
    assert ranges[2] == (50, 25, STATUS_ERROR)
    assert ranges[3] == (75, 25, STATUS_UNTRIED)


def test_iter_filemap_ranges_empty_transitions():
    """Test iter_filemap_ranges handles empty transitions list."""
    filemap = FileMap(100)
    filemap.transitions = []  # Corrupt state

    ranges = list(iter_filemap_ranges(filemap))
    assert ranges == []


def test_iter_filemap_ranges_single_transition():
    """Test iter_filemap_ranges with minimal valid transitions."""
    filemap = FileMap(100)
    # Only the end marker - everything untried
    ranges = list(iter_filemap_ranges(filemap))

    assert len(ranges) == 1
    assert ranges[0] == (0, 100, STATUS_UNTRIED)


def test_iter_filemap_ranges_mixed_statuses(filemap):
    """Test iter_filemap_ranges with multiple different statuses."""
    filemap[0:20] = STATUS_OK
    filemap[20:40] = STATUS_ERROR
    filemap[60:80] = STATUS_OK

    ranges = list(iter_filemap_ranges(filemap))

    assert len(ranges) == 5
    assert ranges[0] == (0, 20, STATUS_OK)
    assert ranges[1] == (20, 20, STATUS_ERROR)
    assert ranges[2] == (40, 20, STATUS_UNTRIED)
    assert ranges[3] == (60, 20, STATUS_OK)
    assert ranges[4] == (80, 20, STATUS_UNTRIED)


def test_iter_filemap_ranges_edge_cases(filemap):
    """Test iter_filemap_ranges with edge cases."""
    # Single byte at start
    filemap[0:1] = STATUS_ERROR
    # Single byte at end
    filemap[99:100] = STATUS_OK
    # Single byte in middle
    filemap[50:51] = STATUS_OK

    ranges = list(iter_filemap_ranges(filemap))

    assert len(ranges) == 5
    assert ranges[0] == (0, 1, STATUS_ERROR)
    assert ranges[1] == (1, 49, STATUS_UNTRIED)
    assert ranges[2] == (50, 1, STATUS_OK)
    assert ranges[3] == (51, 48, STATUS_UNTRIED)
    assert ranges[4] == (99, 1, STATUS_OK)
    # Zero-length ranges are filtered out


def test_parse_status_valid_lines():
    """Test parse_status with valid ddrescue lines."""
    # Test all valid status codes
    assert parse_status("0x00001000  0x00000800  +") == (0x1000, 0x800, STATUS_OK)
    assert parse_status("0x00002000  0x00001000  -") == (0x2000, 0x1000, STATUS_ERROR)
    assert parse_status("0x00003000  0x00000400  ?") == (0x3000, 0x400, STATUS_UNTRIED)
    assert parse_status("0x00004000  0x00000200  /") == (0x4000, 0x200, STATUS_TRIMMED)
    assert parse_status("0x00005000  0x00000100  *") == (0x5000, 0x100, STATUS_SLOW)
    assert parse_status("0x00006000  0x00000080  #") == (0x6000, 0x80, STATUS_SCRAPED)

    # Test with extra whitespace
    assert parse_status("  0x00001000    0x00000800    +  ") == (0x1000, 0x800, STATUS_OK)


def test_parse_status_invalid_status():
    """Test parse_status rejects invalid status codes."""
    with pytest.raises(ValueError, match="Invalid status 'X'"):
        parse_status("0x00001000  0x00000800  X")

    with pytest.raises(ValueError, match="Invalid status 'invalid'"):
        parse_status("0x00001000  0x00000800  invalid")

    # Not enough parts should crash with IndexError (no status field)
    with pytest.raises(IndexError):
        parse_status("0x00001000  0x00000800")


def test_parse_status_malformed_lines():
    """Test parse_status with malformed input."""
    # Not enough parts - should let IndexError crash through
    with pytest.raises(IndexError):
        parse_status("0x00001000  0x00000800")

    with pytest.raises(IndexError):
        parse_status("0x00001000")

    # Invalid hex format - should let ValueError crash through
    with pytest.raises(ValueError):
        parse_status("invalid  0x00000800  +")

    with pytest.raises(ValueError):
        parse_status("0x00001000  invalid  +")


def test_statuses_set():
    """Test that STATUSES contains all valid status codes."""
    expected_statuses = {STATUS_OK, STATUS_ERROR, STATUS_UNTRIED, STATUS_TRIMMED, STATUS_SLOW, STATUS_SCRAPED}
    assert STATUSES == expected_statuses


def test_load_basic_ddrescue_file():
    """Test loading a basic ddrescue mapfile."""
    ddrescue_content = """# Rescue Log created by GNU ddrescue version 1.25
# current_pos   current_status  current_pass
0x00000800      +               1
#  pos  size  status
0x00000000  0x00000400  +
0x00000400  0x00000400  -
"""

    file = StringIO(ddrescue_content)
    comments = []
    filemap = FileMap(4096)  # 4KB device
    config = {}

    load(file, comments, filemap, config)

    # Check pass was loaded
    assert filemap.pass_ == 1

    # Check transitions were loaded correctly
    transitions = list(iter_filemap_ranges(filemap))
    assert len(transitions) == 3
    assert transitions[0] == (0x0, 0x400, STATUS_OK)  # 0-1023: OK
    assert transitions[1] == (0x400, 0x400, STATUS_ERROR)  # 1024-2047: ERROR
    assert transitions[2] == (0x800, 0x800, STATUS_UNTRIED)  # 2048-4095: remaining UNTRIED

    # Check comment was preserved
    assert len(comments) == 1
    assert "GNU ddrescue version 1.25" in comments[0]


def test_load_with_blkcache_config():
    """Test loading file with blkcache config comments."""
    ddrescue_content = """# Test comment
## blkcache: device=/dev/sr0
## blkcache: block_size=2048
# current_pos   current_status  current_pass
0x00001000      ?               2
#  pos  size  status
0x00000000  0x00001000  +
"""

    file = StringIO(ddrescue_content)
    comments = []
    filemap = FileMap(8192)
    config = {}

    load(file, comments, filemap, config)

    # Check config was loaded
    assert config["device"] == "/dev/sr0"
    assert config["block_size"] == "2048"

    # Check pass was loaded
    assert filemap.pass_ == 2

    # Check regular comment was preserved
    assert "# Test comment" in comments


def test_load_skips_header_comments():
    """Test that generated header comments are skipped."""
    ddrescue_content = """# Regular comment to keep
# current_pos   current_status  current_pass
0x00000000      +               1
#  pos  size  status
# Another comment to keep
0x00000000  0x00001000  +
"""

    file = StringIO(ddrescue_content)
    comments = []
    filemap = FileMap(4096)
    config = {}

    load(file, comments, filemap, config)

    # Should keep regular comments but skip header lines
    assert len(comments) == 2
    assert "Regular comment to keep" in comments[0]
    assert "Another comment to keep" in comments[1]
    # Header lines should be filtered out
    for comment in comments:
        assert "current_pos" not in comment
        assert "pos  size  status" not in comment


def test_load_fallback_to_data_line():
    """Test fallback when current_pos line can't be parsed."""
    ddrescue_content = """# Comment
0x00000000  0x00001000  +
"""

    file = StringIO(ddrescue_content)
    comments = []
    filemap = FileMap(8192)  # Make device bigger than data
    config = {}

    load(file, comments, filemap, config)

    # Should parse the line as data since it can't be parsed as current_pos
    transitions = list(iter_filemap_ranges(filemap))
    assert len(transitions) == 2  # OK region + remaining untried
    assert transitions[0] == (0x0, 0x1000, STATUS_OK)
    assert transitions[1] == (0x1000, 0x1000, STATUS_UNTRIED)  # 4096 to 8191


def test_load_empty_file():
    """Test loading empty file."""
    file = StringIO("")
    comments = []
    filemap = FileMap(1024)
    config = {}

    load(file, comments, filemap, config)

    # Should remain in initial state
    assert len(comments) == 0
    assert len(config) == 0
    assert filemap.pass_ == 1  # Default value

    # Only the initial untried transition
    transitions = list(iter_filemap_ranges(filemap))
    assert len(transitions) == 1
    assert transitions[0] == (0, 1024, STATUS_UNTRIED)


def test_load_mixed_content():
    """Test loading file with all types of content."""
    ddrescue_content = """# Initial comment
## blkcache: setting=value

# current_pos   current_status  current_pass
0x00000800      ?               3
#  pos  size  status
0x00000000  0x00000400  +
0x00000400  0x00000200  -
# Middle comment
0x00000600  0x00000200  /
0x00000800  0x00000400  *
# Final comment
"""

    file = StringIO(ddrescue_content)
    comments = []
    filemap = FileMap(4096)
    config = {}

    load(file, comments, filemap, config)

    # Check all components
    assert config["setting"] == "value"
    assert filemap.pass_ == 3
    assert len(comments) == 3  # Initial, middle, final

    transitions = list(iter_filemap_ranges(filemap))
    assert len(transitions) == 5  # 4 data regions + remaining untried
    assert transitions[0] == (0x0, 0x400, STATUS_OK)
    assert transitions[1] == (0x400, 0x200, STATUS_ERROR)
    assert transitions[2] == (0x600, 0x200, STATUS_TRIMMED)
    assert transitions[3] == (0x800, 0x400, STATUS_SLOW)
    assert transitions[4] == (0xC00, 0x400, STATUS_UNTRIED)


def test_save_basic():
    """Test saving a basic filemap to ddrescue format."""
    filemap = FileMap(4096)
    filemap[0:1024] = STATUS_OK
    filemap[1024:2048] = STATUS_ERROR
    filemap[2048:3072] = STATUS_SLOW
    # 3072-4096 remains untried

    comments = ["# Test comment"]
    config = {"device": "/dev/sr0", "block_size": "2048"}

    file = StringIO()
    save(file, comments, filemap, config)

    result = file.getvalue()
    lines = result.strip().split("\n")

    # Check comment preservation
    assert "# Test comment" in lines

    # Check config embedding
    assert "## blkcache: block_size=2048" in lines
    assert "## blkcache: device=/dev/sr0" in lines

    # Check header
    assert "# current_pos   current_status  current_pass" in lines

    # Check current_pos line (should show first untried position and highest priority status)
    pos_line = next(line for line in lines if line.startswith("0x") and not line.startswith("0x0000"))
    assert "0xc00" in pos_line.lower() or "3072" in pos_line  # First untried at 3072
    assert "-" in pos_line  # Error has highest priority

    # Check data lines header
    assert "#  pos  size  status" in lines

    # Check data lines - should have transitions for each region
    data_lines = [line for line in lines if line.startswith("0x0000")]
    assert len(data_lines) == 4  # OK, ERROR, SLOW, UNTRIED regions


def test_save_empty_filemap():
    """Test saving empty filemap (all untried)."""
    filemap = FileMap(1024)
    comments = []
    config = {}

    file = StringIO()
    save(file, comments, filemap, config)

    result = file.getvalue()
    lines = result.strip().split("\n")

    # Should have minimal content
    assert "0x0    ?  1" in result  # pos=0, status=untried, pass=1

    # Should have one data line for the entire untried region
    data_lines = [line for line in lines if line.startswith("0x0000")]
    assert len(data_lines) == 1
    assert "0x00000000  0x00000400  ?" in data_lines[0]  # 1024 bytes = 0x400


def test_save_with_all_statuses():
    """Test saving filemap with all possible status types."""
    filemap = FileMap(6144)  # 6KB to fit all statuses
    filemap[0:1024] = STATUS_OK
    filemap[1024:2048] = STATUS_ERROR
    filemap[2048:3072] = STATUS_UNTRIED
    filemap[3072:4096] = STATUS_TRIMMED
    filemap[4096:5120] = STATUS_SLOW
    filemap[5120:6144] = STATUS_SCRAPED

    comments = ["# All statuses test"]
    config = {"test": "all_statuses"}

    file = StringIO()
    save(file, comments, filemap, config)

    result = file.getvalue()

    # Check all status types appear
    assert "+\n" in result  # OK
    assert "-\n" in result  # ERROR
    assert "?\n" in result  # UNTRIED
    assert "/\n" in result  # TRIMMED
    assert "*\n" in result  # SLOW
    assert "#\n" in result  # SCRAPED

    # Check config
    assert "## blkcache: test=all_statuses" in result


def test_save_preserves_pass():
    """Test that save preserves the filemap pass number."""
    filemap = FileMap(1024)
    filemap.pass_ = 5  # Custom pass number
    filemap[0:512] = STATUS_OK

    file = StringIO()
    save(file, [], filemap, {})

    result = file.getvalue()

    # Should show pass 5 in current_pos line
    lines = result.strip().split("\n")
    pos_line = next(line for line in lines if line.startswith("0x") and not line.startswith("0x0000"))
    assert "5" in pos_line  # Pass number should be 5


def test_save_file_operations():
    """Test that save properly handles file operations (seek, truncate)."""
    filemap = FileMap(1024)
    filemap[0:512] = STATUS_OK

    # Pre-populate file with content
    file = StringIO("old content\nmore old content\n")

    save(file, ["# New content"], filemap, {})

    # File should be truncated and rewritten
    result = file.getvalue()
    assert "old content" not in result
    assert "# New content" in result


def test_roundtrip_basic():
    """Test that load->save->load preserves data."""
    # Original ddrescue content
    original_content = """# Original comment
## blkcache: device=/dev/sr0
# current_pos   current_status  current_pass
0x00000800      -               2
#  pos  size  status
0x00000000  0x00000400  +
0x00000400  0x00000200  -
0x00000600  0x00000200  ?
"""

    # First load
    file1 = StringIO(original_content)
    comments1 = []
    filemap1 = FileMap(2048)
    config1 = {}
    load(file1, comments1, filemap1, config1)

    # Save it back
    file2 = StringIO()
    save(file2, comments1, filemap1, config1)

    # Load it again
    file2.seek(0)
    comments2 = []
    filemap2 = FileMap(2048)
    config2 = {}
    load(file2, comments2, filemap2, config2)

    # Should be identical
    assert filemap1.pass_ == filemap2.pass_
    assert config1 == config2
    assert comments1 == comments2

    # Transitions should match
    transitions1 = list(iter_filemap_ranges(filemap1))
    transitions2 = list(iter_filemap_ranges(filemap2))
    assert transitions1 == transitions2


def test_roundtrip_all_statuses():
    """Test roundtrip with all status types."""
    # Create filemap with all statuses
    filemap1 = FileMap(6144)
    filemap1.pass_ = 3
    filemap1[0:1024] = STATUS_OK
    filemap1[1024:2048] = STATUS_ERROR
    filemap1[2048:3072] = STATUS_UNTRIED
    filemap1[3072:4096] = STATUS_TRIMMED
    filemap1[4096:5120] = STATUS_SLOW
    filemap1[5120:6144] = STATUS_SCRAPED

    comments1 = ["# Test with all statuses", "# Another comment"]
    config1 = {"device": "/dev/sr0", "block_size": "2048", "test": "roundtrip"}

    # Save
    file = StringIO()
    save(file, comments1, filemap1, config1)

    # Load back
    file.seek(0)
    comments2 = []
    filemap2 = FileMap(6144)
    config2 = {}
    load(file, comments2, filemap2, config2)

    # Verify everything matches
    assert filemap1.pass_ == filemap2.pass_
    assert config1 == config2
    assert set(comments1) == set(comments2)  # Order might differ

    # Check all transitions preserved
    transitions1 = list(iter_filemap_ranges(filemap1))
    transitions2 = list(iter_filemap_ranges(filemap2))
    assert transitions1 == transitions2


def test_roundtrip_empty():
    """Test roundtrip with empty/minimal data."""
    filemap1 = FileMap(1024)
    comments1 = []
    config1 = {}

    # Save empty state
    file = StringIO()
    save(file, comments1, filemap1, config1)

    # Load back
    file.seek(0)
    comments2 = []
    filemap2 = FileMap(1024)
    config2 = {}
    load(file, comments2, filemap2, config2)

    # Should be identical
    assert filemap1.pass_ == filemap2.pass_
    assert config1 == config2
    assert comments1 == comments2

    transitions1 = list(iter_filemap_ranges(filemap1))
    transitions2 = list(iter_filemap_ranges(filemap2))
    assert transitions1 == transitions2


def test_roundtrip_preserves_properties():
    """Test that computed properties (pos, status) are preserved through roundtrip."""
    filemap1 = FileMap(4096)
    filemap1[0:1024] = STATUS_OK
    filemap1[1024:2048] = STATUS_ERROR  # Highest priority
    filemap1[2048:3072] = STATUS_SLOW
    # 3072-4096 remains untried (first untried position)

    # Capture original computed properties
    original_pos = filemap1.pos  # Should be 3072
    original_status = filemap1.status  # Should be ERROR (highest priority)

    # Roundtrip
    file = StringIO()
    save(file, [], filemap1, {})
    file.seek(0)

    filemap2 = FileMap(4096)
    load(file, [], filemap2, {})

    # Properties should match
    assert filemap2.pos == original_pos
    assert filemap2.status == original_status


def test_roundtrip_complex_transitions():
    """Test roundtrip with complex overlapping transition patterns."""
    filemap1 = FileMap(8192)
    filemap1.pass_ = 4

    # Create complex pattern
    filemap1[0:1000] = STATUS_OK
    filemap1[500:1500] = STATUS_ERROR  # Overlaps previous
    filemap1[1200:1800] = STATUS_SLOW  # Overlaps error
    filemap1[1700:2000] = STATUS_TRIMMED  # Overlaps slow
    filemap1[3000:4000] = STATUS_SCRAPED  # Gap before this

    config1 = {"complex": "test", "overlaps": "true"}
    comments1 = ["# Complex overlapping test"]

    # Roundtrip
    file = StringIO()
    save(file, comments1, filemap1, config1)
    file.seek(0)

    filemap2 = FileMap(8192)
    comments2 = []
    config2 = {}
    load(file, comments2, filemap2, config2)

    # Should be identical despite complex overlaps
    assert filemap1.pass_ == filemap2.pass_
    assert config1 == config2

    transitions1 = list(iter_filemap_ranges(filemap1))
    transitions2 = list(iter_filemap_ranges(filemap2))
    assert transitions1 == transitions2
