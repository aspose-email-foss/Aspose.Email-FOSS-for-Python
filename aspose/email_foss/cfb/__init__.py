"""Compound File Binary (CFB) container reader package.

This package provides reusable, non-printing APIs for reading
Compound File Binary (CFB) containers.
"""

from .reader import (
    CFBError,
    CFBReader,
    DirectoryEntry,
    Header,
)
from .writer import (
    CFBDocument,
    CFBStorage,
    CFBStream,
    CFBWriter,
    compare_directory_entry_names,
)
from .types import (
    BYTE_ORDER_LITTLE_ENDIAN,
    MAXREGSECT,
    MAXREGSID,
    MINI_STREAM_CUTOFF_SIZE,
    NOSTREAM,
    ROOT_ENTRY_NAME,
    ROOT_STREAM_ID,
    DirectoryColorFlag,
    DirectoryObjectType,
    FileTime,
    SectorMarker,
    SectorNumber,
    StreamId,
)

# Backward-compatible aliases.
DIFSECT = int(SectorMarker.DIFSECT)
FATSECT = int(SectorMarker.FATSECT)
ENDOFCHAIN = int(SectorMarker.ENDOFCHAIN)
FREESECT = int(SectorMarker.FREESECT)

__all__ = [
    "CFBError",
    "CFBReader",
    "DirectoryEntry",
    "DirectoryObjectType",
    "DirectoryColorFlag",
    "Header",
    "CFBDocument",
    "CFBStorage",
    "CFBStream",
    "CFBWriter",
    "compare_directory_entry_names",
    "SectorMarker",
    "SectorNumber",
    "StreamId",
    "FileTime",
    "MAXREGSECT",
    "MAXREGSID",
    "MINI_STREAM_CUTOFF_SIZE",
    "BYTE_ORDER_LITTLE_ENDIAN",
    "ROOT_STREAM_ID",
    "ROOT_ENTRY_NAME",
    "DIFSECT",
    "ENDOFCHAIN",
    "FATSECT",
    "FREESECT",
    "NOSTREAM",
]
