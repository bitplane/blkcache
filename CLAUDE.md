# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

blkcache is a userspace transparent block device cache that uses nbdkit to create a Network Block Storage device in Python, mounts it using FUSE, and creates a mmapped disk cache of sectors as they're read. The main purpose is to avoid reading disks (like CDs) multiple times during operations like filesystem dumps and disk rescue operations.

## Architecture

The project follows a layered architecture:

1. **Main Entry Point** (`main.py`): CLI interface that manages device monitoring and server lifecycle
2. **Server Layer** (`server.py`): Orchestrates nbdkit, nbdfuse, and FUSE mounting
3. **Plugin Layer** (`plugin.py`): nbdkit Python plugin that handles block device operations
4. **Cache Layer** (`cache/`): Abstract caching interface and implementations
5. **DiskMap** (`diskmap.py`): ddrescue-compatible mapfile handling for tracking read status

The cache implementation appears to be in transition from a legacy global state approach to a more modular `Cache` class architecture.

## Development Commands

```bash
# Create/activate virtual environment
make install

# Install dev dependencies
make dev

# Run tests
make test
# or directly: scripts/test.sh

# Run tests with coverage
make coverage

# Do not run make documentation unless asked.
# As this pushes to an external site.
make docs

# Build distribution
make dist

# Clean build artifacts
make clean
```

## Testing

Tests use pytest (functional style, not unittest OOP style). Test files mirror the source structure:
- Tests are in `tests/unit/`
- Test files are named `test_<module>.py`
- Tests should be short, well-named, and serve as executable documentation

## Key Technical Considerations

1. **Data Integrity**: This is a disk-level project - NEVER corrupt data. Better to crash with dignity than hide harmful bugs.
2. **Block Size**: Default is 4KB, but can be auto-detected based on device type or specified manually
3. **Caching**: Uses memory-mapped files for sector caching
4. **Disk Status Tracking**: Compatible with ddrescue format for tracking read status
5. **Transitions**: The DiskMap uses a transition-based approach for efficiently representing block states

## Code Style

- Python 3.10+ with type hints where appropriate. i.e. dict[] rather than Dict[]
- Line length: 120 characters
- Use ruff for linting
- Modern pytest tests (functional style)
- Avoid unnecessary mocking - change code structure instead
- Keep logic flat and use descriptive variable names for conditions
