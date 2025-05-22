"""
Disk mapping and status tracking in ddrescue-compatible format.
"""

import bisect
import logging
from pathlib import Path
from typing import Dict, List, TextIO

# Used to prevent sorting by anything other than position
NO_SORT = float("nan")

# Block status codes (ddrescue compatible)
STATUS_OK = "+"  # Successfully read
STATUS_ERROR = "-"  # Read error
STATUS_UNTRIED = "?"  # Not tried yet
STATUS_TRIMMED = "/"  # Trimmed (not tried because of read error)
STATUS_SLOW = "*"  # Non-trimmed, non-scraped (slow reads)
STATUS_SCRAPED = "#"  # Non-trimmed, scraped (slow reads completed)

# Version of the rescue log format
FORMAT_VERSION = "1.0"

log = logging.getLogger(__name__)


class DiskMap:
    """
    Handles ddrescue-compatible mapfile processing for block device recovery.

    Uses transitions to efficiently represent block states across the device.
    """

    def __init__(self, map_path: Path, size: int):
        """Initialize with the path to a mapfile and device size."""
        self.map_path = map_path
        self.comments: List[str] = []
        self.config: Dict[str, str] = {}

        # Store device size in config
        self.config["device_size"] = str(size)

        # State tracking
        self.size = size
        self.current_pass = 1
        self.current_status = STATUS_UNTRIED
        self.current_pos = 0

        # Transitions list: (position, NO_SORT, status)
        # Each entry marks where status changes
        # Initialize with empty device (all untried), with a duplicate status at the end
        # for ease of insert
        self.transitions = [(0, NO_SORT, STATUS_UNTRIED), (size, NO_SORT, STATUS_UNTRIED)]

        # Load existing mapfile if it exists
        if self.map_path.exists():
            self.read()

    def read(self) -> None:
        """Read and parse a ddrescue mapfile."""
        self.comments = []
        self.config = {}
        current_pos_line_found = False

        # Reset transitions to initial state before reading
        self.transitions = [(0, NO_SORT, STATUS_UNTRIED), (self.size, NO_SORT, STATUS_UNTRIED)]

        with self.map_path.open("r") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("## blkcache:"):
                    # Process blkcache config comments - no try/except, let errors bubble up
                    config_line = line[12:].strip()
                    key, value = config_line.split("=", 1)
                    self.config[key.strip()] = value.strip()

                elif line.startswith("#"):
                    # Skip comment headers we'll regenerate
                    if "current_pos" in line and "current_status" in line and "current_pass" in line:
                        continue
                    if " pos " in line and " size " in line and " status" in line:
                        continue

                    # Store all other comment lines
                    self.comments.append(line)

                elif not current_pos_line_found and len(line.split()) >= 3:
                    # First non-comment, non-config line is the current_pos line
                    parts = line.split()
                    try:
                        self.current_pos = int(parts[0], 16)
                        self.current_status = parts[1]
                        self.current_pass = int(parts[2])
                        current_pos_line_found = True
                    except (ValueError, IndexError):
                        # If we can't parse this line, assume it's a normal data line
                        self._process_data_line(line)

                else:
                    # Process normal data lines
                    self._process_data_line(line)

        # Ensure we always have the final boundary transition
        if not self.transitions or self.transitions[-1][0] != self.size:
            self.transitions.append((self.size, NO_SORT, STATUS_UNTRIED))

    def _process_data_line(self, line: str) -> None:
        """Process a data line with pos/size/status format."""
        parts = line.split()
        # Let it crash if not enough parts or invalid format
        start = int(parts[0], 16)
        length = int(parts[1], 16)
        status = parts[2]
        end = start + length - 1

        # Set status for this range
        self.set_status(start, end, status)

    def write(self) -> None:
        """Write current state to the mapfile."""
        log.debug("Writing diskmap to %s", self.map_path)
        log.debug("Diskmap has %d transitions", len(self.transitions))

        with self.map_path.open("w") as file:
            # Comments come first
            for comment in self.comments:
                file.write(f"{comment}\n")

            # Embed our config into comments
            for key, val in sorted(self.config.items()):
                file.write(f"## blkcache: {key}={val}\n")

            # write the main header. todo: use %-10s or something?
            file.write("# current_pos   current_status  current_pass\n")
            file.write(f"0x{self.current_pos:x}    {self.current_status}  {self.current_pass}\n")

            # Write transition data. fixme:
            file.write("#  pos  size  status\n")
            self._write_data_rows(file)

    def _write_data_rows(self, file: TextIO) -> None:
        """Write data rows derived from transitions."""
        if not self.transitions:
            return

        # Process transitions to write ranges
        for i in range(len(self.transitions) - 1):
            start = self.transitions[i][0]
            end = self.transitions[i + 1][0] - 1
            status = self.transitions[i][2]

            length = end - start + 1

            file.write(f"0x{start:08x}  0x{length:08x}  {status}\n")

    def set_status(self, start: int, end: int, status: str) -> None:
        """Set the status for a range of blocks."""
        log.debug("Setting status %s for range [%d, %d]", status, start, end)

        # Input validation
        if start < 0 or end >= self.size:
            raise ValueError(f"Range [{start}, {end}] is outside of device range [0, {self.size - 1}]")
        if start > end:
            raise ValueError(f"Invalid range: start ({start}) > end ({end})")

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
