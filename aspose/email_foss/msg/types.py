from __future__ import annotations

from dataclasses import dataclass


# Required name for the property stream in all MSG storages except Named Property Mapping storage.
PROPERTY_STREAM_NAME = "__properties_version1.0"
# Prefix used to form stream names for variable-length and multi-valued property values.
PROPERTY_VALUE_STREAM_PREFIX = "__substg1.0_"
# Prefix for recipient object storage names; suffix is 8-digit hexadecimal index.
RECIPIENT_STORAGE_PREFIX = "__recip_version1.0_#"
# Prefix for attachment object storage names; suffix is 8-digit hexadecimal index.
ATTACHMENT_STORAGE_PREFIX = "__attach_version1.0_#"
# Substorage name under attachment storage that contains an embedded message object.
EMBEDDED_MESSAGE_STORAGE_NAME = "__substg1.0_3701000D"
# Required storage name for named property mapping streams.
NAMED_PROPERTY_MAPPING_STORAGE_NAME = "__nameid_version1.0"
# Maximum number of recipient object storages in one MSG file.
MAX_RECIPIENT_STORAGES = 2048
# Maximum number of attachment object storages in one MSG file.
MAX_ATTACHMENT_STORAGES = 2048
# Property must not be deleted from MSG file.
PROPATTR_MANDATORY = 0x00000001
# If clear, property must not be read.
PROPATTR_READABLE = 0x00000002
# If clear, property must not be modified or deleted.
PROPATTR_WRITABLE = 0x00000004


@dataclass(frozen=True)
class PropertyStreamHeaderTopLevel:
    """Top-level property stream header containing next-id counters and counts for recipients and attachments."""

    # Reserved bytes in top-level property stream header; written as zero and ignored when reading.
    reserved_0: bytes
    # Identifier to use for naming the next recipient storage if one is created.
    next_recipient_id: int
    # Identifier to use for naming the next attachment storage if one is created.
    next_attachment_id: int
    # Number of recipient objects represented in this message.
    recipient_count: int
    # Number of attachment objects represented in this message.
    attachment_count: int
    # Trailing reserved bytes in top-level property stream header; written as zero and ignored when reading.
    reserved_1: bytes = b""


@dataclass(frozen=True)
class PropertyStreamHeaderSubobject:
    """Property stream header used in recipient and attachment storages, containing only reserved bytes."""

    # Reserved bytes in recipient/attachment property stream header; written as zero and ignored when reading.
    reserved_0: bytes


@dataclass(frozen=True)
class PropertyEntryFixedLength:
    """Fixed-length property stream entry containing property tag, flags, and inline 8-byte value payload."""

    # Property tag identifying property id and property type.
    property_tag: int
    # Property attribute flags describing mandatory/readable/writable behavior.
    flags: int
    # Inline fixed-length value payload for fixed-length property entries.
    value: bytes

    def is_mandatory(self) -> bool:
        return (self.flags & PROPATTR_MANDATORY) != 0

    def is_readable(self) -> bool:
        return (self.flags & PROPATTR_READABLE) != 0

    def is_writable(self) -> bool:
        return (self.flags & PROPATTR_WRITABLE) != 0
