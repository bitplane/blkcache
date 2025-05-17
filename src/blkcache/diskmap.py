"""
Disk mapping and status tracking in ddrescue-compatible format.
"""

import bisect
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

        start_key = (start, NO_SORT, status)
        end_key = (end + 1, NO_SORT, STATUS_UNTRIED)

        start_idx = bisect.bisect_left(self.transitions, start_key)
        end_idx = min(bisect.bisect_right(self.transitions, end_key), len(self.transitions) - 1)

        before_idx = 0 if self.transitions[start_idx][0] == start else start_idx - 1
        after_idx = end_idx if self.transitions[end_idx][0] == end + 1 else end_idx + 1
        before_idx = min(max(before_idx, 0), len(self.transitions) - 1)
        after_idx = min(max(after_idx, 0), len(self.transitions) - 1)
        after_status = self.transitions[after_idx][2]

        mix = {
            self.transitions[before_idx][0]: self.transitions[before_idx],
            start: start_key,
            self.transitions[after_idx][0]: self.transitions[after_idx],
            end: (end + 1, NO_SORT, after_status),
        }

        splice = sorted(list(mix.values()))
        self.transitions[before_idx:after_idx] = splice
