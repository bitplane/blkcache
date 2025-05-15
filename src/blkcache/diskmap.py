"""
Disk mapping and status tracking in ddrescue-compatible format.
"""

import bisect
from pathlib import Path
from typing import Dict, List, Tuple, TextIO, Optional

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

    def __init__(self, map_path: Path, size: Optional[int] = None):
        """Initialize with the path to a mapfile and optional device size."""
        self.map_path = map_path
        self.comments: List[str] = []
        self.config: Dict[str, str] = {}

        # State tracking
        self.current_pass = 1
        self.current_status = STATUS_UNTRIED
        self.current_pos = 0

        # Transitions list: (position, NO_SORT, status)
        # Each entry marks where status changes
        self.transitions: List[Tuple[int, float, str]] = []

        # Initialize with unknown state if size is provided
        if size is not None:
            self.transitions = [(0, NO_SORT, STATUS_UNTRIED)]

        # Load existing mapfile if it exists
        if self.map_path.exists():
            self.read()

    def read(self) -> None:
        """Read and parse a ddrescue mapfile."""
        self.comments = []
        self.config = {}
        self.transitions = []
        current_pos_line_found = False

        with self.map_path.open("r") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("# "):
                    # Skip specific header comment lines
                    if "current_pos" in line and "current_status" in line and "current_pass" in line:
                        continue
                    if " pos " in line and " size " in line and " status" in line:
                        continue

                    # Store the full comment line
                    self.comments.append(line)

                elif line.startswith("## blkcache:"):
                    # Process blkcache config comments
                    try:
                        config_line = line[12:].strip()
                        key, value = config_line.split("=", 1)
                        self.config[key.strip()] = value.strip()
                    except ValueError:
                        pass  # Ignore malformed config lines

                elif line.startswith("#"):
                    # Skip other comment lines
                    continue

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
        if len(parts) >= 3:
            try:
                start = int(parts[0], 16)
                length = int(parts[1], 16)
                status = parts[2]
                end = start + length - 1

                # Set status for this range
                self.set_status(start, end, status)
            except (ValueError, IndexError):
                # Skip malformed lines
                pass

    def write(self) -> None:
        """Write current state to the mapfile."""
        with self.map_path.open("w") as file:
            # 1. Write comments
            for comment in self.comments:
                file.write(f"{comment}\n")

            # 2. Write blkcache config as comments
            for key, val in sorted(self.config.items()):
                file.write(f"## blkcache: {key}={val}\n")

            # 3. Write the current_pos header
            file.write("# current_pos  current_status  current_pass\n")

            # 4. Write current position/status/pass
            file.write(f"0x{self.current_pos:x}     {self.current_status}               {self.current_pass}\n")

            # 5. Write the pos/size/status header
            file.write("#      pos        size  status\n")

            # 6. Write the data rows from transitions
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

            # Calculate length
            length = end - start + 1

            # Skip empty ranges
            if length <= 0:
                continue

            # Write the range
            file.write(f"0x{start:08x}  0x{length:08x}  {status}\n")

        # Write the last range if device_size is known
        if "device_size" in self.config:
            last_pos = self.transitions[-1][0]
            last_status = self.transitions[-1][2]
            device_size = int(self.config["device_size"])

            # Only write if there's space left
            if last_pos < device_size:
                length = device_size - last_pos
                file.write(f"0x{last_pos:08x}  0x{length:08x}  {last_status}\n")

    def set_status(self, start: int, end: int, status: str) -> None:
        """Set the status for a range of blocks."""
        if not self.transitions:
            # First transition at start position
            self.transitions = [(start, NO_SORT, status)]

            # Add end transition if needed (if the range doesn't cover the whole device)
            if end < float("inf"):
                self.transitions.append((end + 1, NO_SORT, STATUS_UNTRIED))
            return

        # Find insertion points using binary search
        positions = [t[0] for t in self.transitions]
        start_idx = bisect.bisect_right(positions, start)
        end_idx = bisect.bisect_left(positions, end + 1)

        # Get status before and after our range
        before_status = self.get_status_at(start - 1)
        after_status = self.get_status_at(end + 1)

        # Prepare new transitions for splicing
        new_transitions = []

        # Add start transition if status changes
        if start_idx == 0 or self.transitions[start_idx - 1][2] != status:
            new_transitions.append((start, NO_SORT, status))

        # Add end transition if status changes back
        if end < float("inf") and after_status != status:
            new_transitions.append((end + 1, NO_SORT, after_status))

        # Perform the splice operation - O(log n) insertion
        self.transitions[start_idx:end_idx] = new_transitions

        # Clean up adjacent transitions with same status
        self._cleanup_transitions()

    def _cleanup_transitions(self) -> None:
        """Remove redundant transitions with same status."""
        if len(self.transitions) <= 1:
            return

        # In-place cleanup
        i = 1
        while i < len(self.transitions):
            if self.transitions[i][2] == self.transitions[i - 1][2]:
                # Remove redundant transition
                self.transitions.pop(i)
            else:
                i += 1

    def get_status_at(self, pos: int) -> str:
        """Get the status at a specific position."""
        if not self.transitions:
            return STATUS_UNTRIED

        # Find the last transition before or at this position
        idx = bisect.bisect_right([t[0] for t in self.transitions], pos)

        if idx == 0:
            # Position is before first transition
            return STATUS_UNTRIED

        # Return status from the last transition before this position
        return self.transitions[idx - 1][2]
