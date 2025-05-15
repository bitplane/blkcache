"""
Constants and configuration values for the blkcache system.
"""

# Linux ioctl constants
BLKGETSIZE64 = 0x80081272  # <linux/fs.h> Get device byte-length
BLKSSZGET = 0x1268  # Get block device sector size
CDROM_GET_BLKSIZE = 0x5313  # Get CDROM block size

# Block status codes (ddrescue compatible)
STATUS_OK = "+"  # Successfully read
STATUS_ERROR = "-"  # Read error
STATUS_UNTRIED = "?"  # Not tried yet
STATUS_TRIMMED = "/"  # Trimmed (not tried because of read error)
STATUS_SLOW = "*"  # Non-trimmed, non-scraped (slow reads)
STATUS_SCRAPED = "#"  # Non-trimmed, scraped (slow reads completed)

# Default block size (commonly used for CD/DVD media)
DEFAULT_BLOCK_SIZE = 2048

# Version of the rescue log format
FORMAT_VERSION = "1.0"
