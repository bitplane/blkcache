"""
ddrescue file format loading and saving.

Functions to read/write ddrescue-compatible mapfiles with comments,
config, and FileMap data.
"""

import logging
from typing import Dict, List

from .file.filemap import FileMap, STATUSES

# Version of the rescue log format
FORMAT_VERSION = "1.0"

log = logging.getLogger(__name__)


def iter_filemap_ranges(filemap: FileMap):
    """Iterate over FileMap transitions yielding (pos, size, status) tuples."""
    if not filemap.transitions:
        return

    # Process transitions to yield ranges
    for i in range(len(filemap.transitions) - 1):
        start = filemap.transitions[i][0]
        end = filemap.transitions[i + 1][0] - 1
        status = filemap.transitions[i][2]

        size = end - start + 1
        if size > 0:  # Skip zero-length ranges
            yield (start, size, status)


def load(file, comments: List[str], filemap: FileMap, config: Dict[str, str]) -> None:
    """Load ddrescue mapfile from file-like object, updating provided containers."""
    current_pos_line_found = False

    for line in file:
        line = line.strip()
        if not line:
            continue

        if line.startswith("## blkcache:"):
            # Process blkcache config comments
            config_line = line[12:].strip()
            key, value = config_line.split("=", 1)
            config[key.strip()] = value.strip()

        elif line.startswith("#"):
            # Skip comment headers we'll regenerate
            if "current_pos" in line and "current_status" in line and "current_pass" in line:
                continue
            if " pos " in line and " size " in line and " status" in line:
                continue

            # Add to comment lines
            comments.append(line)

        elif not current_pos_line_found and len(line.split()) >= 3:
            # First non-comment, non-config line is the current_pos line
            parts = line.split()
            try:
                # Parse but ignore current_pos and current_status - we compute them
                filemap.pass_ = int(parts[2])
                current_pos_line_found = True
            except (ValueError, IndexError):
                # If we can't parse this line, assume it's a normal data line
                start, size, status = parse_status(line)
                filemap[start : start + size] = status

        else:
            # Process normal data lines
            start, size, status = parse_status(line)
            filemap[start : start + size] = status


def save(
    file,
    comments: List[str],
    filemap: FileMap,
    config: Dict[str, str],
) -> None:
    """Save ddrescue mapfile to file-like object from provided containers."""
    log.debug("Saving ddrescue format with %d transitions", len(filemap.transitions))

    file.seek(0)
    file.truncate()

    # Comments come first
    for comment in comments:
        file.write(f"{comment}\n")

    # Embed our config into comments
    for key, val in sorted(config.items()):
        file.write(f"## blkcache: {key}={val}\n")

    # Write the main header
    file.write("# current_pos   current_status  current_pass\n")
    file.write(f"0x{filemap.pos:x}    {filemap.status}  {filemap.pass_}\n")

    # Write transition data
    file.write("#  pos  size  status\n")
    for pos, size, status in iter_filemap_ranges(filemap):
        file.write(f"0x{pos:08x}  0x{size:08x}  {status}\n")


def parse_status(line: str) -> tuple[int, int, str]:
    """Parse a status line returning (start, size, status)."""
    parts = line.split()
    # Let it crash if not enough parts or invalid format
    start = int(parts[0], 16)
    size = int(parts[1], 16)
    status = parts[2]

    # Validate status is one we recognize
    if status not in STATUSES:
        raise ValueError(f"Invalid status '{status}' in line: {line.strip()}")

    return start, size, status
