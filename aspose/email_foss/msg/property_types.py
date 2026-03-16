from __future__ import annotations

from enum import IntEnum


class PropertyTypeCode(IntEnum):
    """MAPI property type codes used in MSG property tags and value stream names."""

    # 16-bit signed integer property value type.
    PTYP_INTEGER16 = 0x0002
    # 32-bit signed integer property value type.
    PTYP_INTEGER32 = 0x0003
    # 32-bit floating-point property value type.
    PTYP_FLOATING32 = 0x0004
    # 64-bit floating-point property value type.
    PTYP_FLOATING64 = 0x0005
    # Currency property value type stored as scaled 64-bit integer.
    PTYP_CURRENCY = 0x0006
    # Floating-time property value type stored as 64-bit double.
    PTYP_FLOATINGTIME = 0x0007
    # 32-bit error code property value type.
    PTYP_ERRORCODE = 0x000A
    # Boolean property value type.
    PTYP_BOOLEAN = 0x000B
    # Object property value type.
    PTYP_OBJECT = 0x000D
    # 64-bit signed integer property value type.
    PTYP_INTEGER64 = 0x0014
    # 8-bit string property value type.
    PTYP_STRING8 = 0x001E
    # Unicode string property value type.
    PTYP_STRING = 0x001F
    # FILETIME-based date/time property value type.
    PTYP_TIME = 0x0040
    # GUID property value type.
    PTYP_GUID = 0x0048
    # Binary property value type.
    PTYP_BINARY = 0x0102
    # Multiple-valued 16-bit integer property value type.
    PTYP_MULTIPLE_INTEGER16 = 0x1002
    # Multiple-valued 32-bit integer property value type.
    PTYP_MULTIPLE_INTEGER32 = 0x1003
    # Multiple-valued 32-bit floating-point property value type.
    PTYP_MULTIPLE_FLOATING32 = 0x1004
    # Multiple-valued 64-bit floating-point property value type.
    PTYP_MULTIPLE_FLOATING64 = 0x1005
    # Multiple-valued currency property value type.
    PTYP_MULTIPLE_CURRENCY = 0x1006
    # Multiple-valued floating-time property value type.
    PTYP_MULTIPLE_FLOATINGTIME = 0x1007
    # Multiple-valued 64-bit integer property value type.
    PTYP_MULTIPLE_INTEGER64 = 0x1014
    # Multiple-valued 8-bit string property value type.
    PTYP_MULTIPLE_STRING8 = 0x101E
    # Multiple-valued Unicode string property value type.
    PTYP_MULTIPLE_STRING = 0x101F
    # Multiple-valued FILETIME property value type.
    PTYP_MULTIPLE_TIME = 0x1040
    # Multiple-valued GUID property value type.
    PTYP_MULTIPLE_GUID = 0x1048
    # Multiple-valued binary property value type.
    PTYP_MULTIPLE_BINARY = 0x1102
