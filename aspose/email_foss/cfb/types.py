from __future__ import annotations

from enum import IntEnum
from typing import NewType


# Semantic aliases from KB primitive mappings.
SectorNumber = NewType("SectorNumber", int)
StreamId = NewType("StreamId", int)
FileTime = NewType("FileTime", int)


# Constants from KB entities.
# Maximum regular sector number (0xFFFFFFFA).
MAXREGSECT = 0xFFFFFFFA
# Maximum regular stream ID (0xFFFFFFFA).
MAXREGSID = 0xFFFFFFFA
# Terminator or empty pointer (0xFFFFFFFF).
NOSTREAM = 0xFFFFFFFF
# Maximum stream size allocated from the mini FAT and mini stream.
MINI_STREAM_CUTOFF_SIZE = 4096
# Byte-order marker for little-endian integer encoding.
BYTE_ORDER_LITTLE_ENDIAN = 0xFFFE
# Stream ID of the root directory entry in the first directory sector.
ROOT_STREAM_ID = 0
# Required UTF-16 null-terminated name for the root storage directory entry.
ROOT_ENTRY_NAME = "Root Entry"


class SectorMarker(IntEnum):
    """Special FAT marker values reserved for sector allocation metadata."""

    # 0xFFFFFFFC marker identifying a sector that belongs to the DIFAT chain.
    DIFSECT = 0xFFFFFFFC
    # 0xFFFFFFFD marker identifying a sector that belongs to the FAT itself.
    FATSECT = 0xFFFFFFFD
    # 0xFFFFFFFE marker indicating the final sector in a chain.
    ENDOFCHAIN = 0xFFFFFFFE
    # 0xFFFFFFFF marker indicating an unallocated sector.
    FREESECT = 0xFFFFFFFF


class DirectoryObjectType(IntEnum):
    """Classifies the directory entry payload as unallocated, storage, stream, or root storage."""

    # Directory entry is unallocated or has an unknown object type.
    UNKNOWN_OR_UNALLOCATED = 0
    # Directory entry represents a storage object that can contain child entries.
    STORAGE_OBJECT = 1
    # Directory entry represents a stream object that stores byte data.
    STREAM_OBJECT = 2
    # Directory entry represents the root storage object for the compound file.
    ROOT_STORAGE_OBJECT = 5


class DirectoryColorFlag(IntEnum):
    """Stores the red-black tree color used by directory sibling links."""

    # Directory entry node is red in the sibling red-black tree.
    RED = 0
    # Directory entry node is black in the sibling red-black tree.
    BLACK = 1
