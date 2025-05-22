"""
File mapping for tracking block/sector status.

Pure data structure for tracking status of byte ranges without
any file format dependencies.
"""

import bisect
import logging

# Used to prevent sorting by anything other than position
NO_SORT = float("nan")

# Block status codes
STATUS_OK = "+"  # Successfully read
STATUS_ERROR = "-"  # Read error
STATUS_UNTRIED = "?"  # Not tried yet
STATUS_TRIMMED = "/"  # Trimmed (not tried because of read error)
STATUS_SLOW = "*"  # Non-trimmed, non-scraped (slow reads)
STATUS_SCRAPED = "#"  # Non-trimmed, scraped (slow reads completed)

log = logging.getLogger(__name__)


class FileMap:
    """
    Tracks status of byte ranges using efficient transition-based representation.

    Pure data structure with no file format dependencies.
    Uses slice notation: filemap[start:end] = status
    """

    def __init__(self, size: int):
        """Initialize with device/file size."""
        self.size = size
        self.pass_ = 1  # ddrescue compatibility

        # Transitions list: (position, NO_SORT, status)
        # Each entry marks where status changes
        # Initialize with empty device (all untried), with a duplicate status at the end
        # for ease of insert
        self.transitions = [(0, NO_SORT, STATUS_UNTRIED), (size, NO_SORT, STATUS_UNTRIED)]

    def __setitem__(self, key, status):
        """Set status for range using slice notation: filemap[start:end] = status"""
        if isinstance(key, slice):
            # Check bounds before calling indices() which clamps values
            if key.start is not None and key.start < 0:
                raise ValueError(f"Negative start index: {key.start}")
            if key.stop is not None and key.stop > self.size:
                raise ValueError(f"Stop index beyond device size: {key.stop} > {self.size}")

            start, stop, step = key.indices(self.size)
            if step != 1:
                raise ValueError("Step not supported")
            self._set_status_range(start, stop - 1, status)
        else:
            # Single offset
            self._set_status_range(key, key, status)

    def __iter__(self):
        """Iterate over transitions yielding (pos, size, status) tuples."""
        if not self.transitions:
            return

        # Process transitions to yield ranges
        for i in range(len(self.transitions) - 1):
            start = self.transitions[i][0]
            end = self.transitions[i + 1][0] - 1
            status = self.transitions[i][2]

            size = end - start + 1
            if size > 0:  # Skip zero-length ranges
                yield (start, size, status)

    def _set_status_range(self, start: int, end: int, status: str) -> None:
        """Set the status for a range of bytes."""
        log.debug("Setting status %s for range [%d, %d]", status, start, end)

        start_key = (start, NO_SORT, status)
        end_key = (end + 1, NO_SORT, STATUS_UNTRIED)

        # Find indices using binary search
        start_idx = bisect.bisect_left(self.transitions, start_key)
        end_idx = bisect.bisect_right(self.transitions, end_key)

        # Determine before and after indices
        before_idx = max(start_idx - 1, 0)
        after_idx = min(end_idx, len(self.transitions) - 1)

        # Get the 5 variables we need
        before_status = self.transitions[before_idx][2]  # before_start.status
        before_pos = self.transitions[before_idx][0]  # before_start.pos
        after_status = self.transitions[after_idx][2]  # after.status
        after_pos = self.transitions[after_idx][0]  # after.pos

        # Find before_end: what status exists at end+1 position before our change
        before_end_idx = max(0, end_idx - 1)
        before_end_status = self.transitions[before_end_idx][2]

        splice = []
        if before_pos == start:
            # overwrite the start position
            splice.append(start_key)
        else:
            splice.append((before_pos, NO_SORT, before_status))
            if before_status != status:
                # if the status is different, we need to add a new entry
                splice.append(start_key)

        if before_end_status != status:
            splice.append((end + 1, NO_SORT, before_end_status))
        if end + 1 < after_pos:
            splice.append((after_pos, NO_SORT, after_status))

        self.transitions[before_idx : after_idx + 1] = splice

    @property
    def pos(self) -> int:
        """Current position - first untried byte."""
        for position, _, status in self.transitions:
            if status == STATUS_UNTRIED:
                return position
        raise ValueError("FileMap transitions corrupted, someone deleted the end one.")

    @property
    def status(self) -> str:
        """Current status - highest priority status found in transitions."""
        if len(self.transitions) < 2:
            raise ValueError("FileMap transitions corrupted - insufficient entries")

        # ddrescue priority order: error > untried > trimmed > slow > scraped > ok
        priority_order = [STATUS_ERROR, STATUS_UNTRIED, STATUS_TRIMMED, STATUS_SLOW, STATUS_SCRAPED, STATUS_OK]

        statuses = {self.transitions[i][2] for i in range(len(self.transitions) - 1)}

        for status in priority_order:
            if status in statuses:
                return status

        raise ValueError("FileMap transitions corrupted - no valid statuses found")
