from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple

from ..cfb import CFBReader, DirectoryEntry, ROOT_STREAM_ID

from .types import (
    ATTACHMENT_STORAGE_PREFIX,
    EMBEDDED_MESSAGE_STORAGE_NAME,
    MAX_ATTACHMENT_STORAGES,
    MAX_RECIPIENT_STORAGES,
    NAMED_PROPERTY_MAPPING_STORAGE_NAME,
    PROPERTY_STREAM_NAME,
    RECIPIENT_STORAGE_PREFIX,
    PropertyEntryFixedLength,
    PropertyStreamHeaderSubobject,
    PropertyStreamHeaderTopLevel,
)


class MsgError(Exception):
    """Raised for malformed or unsupported MSG structures."""


@dataclass(frozen=True)
class StorageLayout:
    """Naming and containment rules for recipient, attachment, embedded message, and nameid storages."""

    recipient_storages: Tuple[DirectoryEntry, ...]
    attachment_storages: Tuple[DirectoryEntry, ...]
    named_property_mapping_storage: DirectoryEntry
    top_level_property_stream: DirectoryEntry


class MsgReader:
    """Normative top-level MSG containment and stream requirements for container traversal."""

    PROPERTY_STREAM_HEADER_TOP_LEVEL_LAYOUT: Dict[str, Tuple[int, int]] = {
        "reserved_0": (0, 8),
        "next_recipient_id": (8, 4),
        "next_attachment_id": (12, 4),
        "recipient_count": (16, 4),
        "attachment_count": (20, 4),
        "reserved_1": (24, 8),
    }
    PROPERTY_STREAM_HEADER_SUBOBJECT_LAYOUT: Dict[str, Tuple[int, int]] = {
        "reserved_0": (0, 8),
    }
    PROPERTY_ENTRY_FIXED_LENGTH_LAYOUT: Dict[str, Tuple[int, int]] = {
        "property_tag": (0, 4),
        "flags": (4, 4),
        "value": (8, 8),
    }

    _RECIPIENT_NAME_RE = re.compile(r"^__recip_version1\.0_#[0-9A-Fa-f]{8}$")
    _ATTACHMENT_NAME_RE = re.compile(r"^__attach_version1\.0_#[0-9A-Fa-f]{8}$")

    def __init__(self, cfb_reader: CFBReader, *, strict: bool = False) -> None:
        self._cfb = cfb_reader
        self._strict = strict
        self._closed = False
        self._validation_issues: List[str] = []
        self._layout = self._build_storage_layout()
        top_level_data = self._cfb.get_stream_data(self._layout.top_level_property_stream.stream_id)
        self.top_level_header, self._top_level_fixed_entries = self.parse_top_level_property_stream(top_level_data)
        self._validate_top_level_counts()
        self._validate_embedded_message_rules()

    @classmethod
    def from_file(cls, path: Path | str, *, strict: bool = False) -> "MsgReader":
        return cls(CFBReader.from_file(path), strict=strict)

    @property
    def cfb_reader(self) -> CFBReader:
        if self._closed:
            raise MsgError("MsgReader is closed.")
        return self._cfb

    @property
    def storage_layout(self) -> StorageLayout:
        return self._layout

    @property
    def strict(self) -> bool:
        return self._strict

    @property
    def validation_issues(self) -> Tuple[str, ...]:
        return tuple(self._validation_issues)

    def close(self) -> None:
        if self._closed:
            return
        self._cfb.close()
        self._closed = True

    def __enter__(self) -> "MsgReader":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def iter_top_level_fixed_length_properties(self) -> Iterator[PropertyEntryFixedLength]:
        for entry in self._top_level_fixed_entries:
            yield entry

    def iter_recipient_storages(self) -> Iterator[DirectoryEntry]:
        for entry in self._layout.recipient_storages:
            yield entry

    def iter_attachment_storages(self) -> Iterator[DirectoryEntry]:
        for entry in self._layout.attachment_storages:
            yield entry

    def parse_message_property_stream(
        self, storage_stream_id: int = ROOT_STREAM_ID
    ) -> Tuple[PropertyStreamHeaderTopLevel, List[PropertyEntryFixedLength]]:
        """Read the property stream in the top level or an embedded-message storage."""
        if storage_stream_id == ROOT_STREAM_ID:
            data = self._cfb.get_stream_data(self._layout.top_level_property_stream.stream_id)
        else:
            property_stream = self._get_single_property_stream_entry(storage_stream_id)
            data = self._cfb.get_stream_data(property_stream.stream_id)
        return self.parse_top_level_property_stream(data)

    def parse_subobject_property_stream(
        self, storage_stream_id: int
    ) -> Tuple[PropertyStreamHeaderSubobject, List[PropertyEntryFixedLength]]:
        """Read the property stream in recipient/attachment storage and decode fixed-length entries."""
        property_stream = self._get_single_property_stream_entry(storage_stream_id)
        data = self._cfb.get_stream_data(property_stream.stream_id)
        return self.parse_subobject_property_stream_data(data)

    @classmethod
    def parse_top_level_property_stream(
        cls, data: bytes
    ) -> Tuple[PropertyStreamHeaderTopLevel, List[PropertyEntryFixedLength]]:
        """Decode top-level property stream header and fixed-length entries."""
        if len(data) < 32:
            raise MsgError("Top-level property stream is smaller than 32-byte header.")
        reserved_0 = data[0:8]
        next_recipient_id = struct.unpack_from("<I", data, 8)[0]
        next_attachment_id = struct.unpack_from("<I", data, 12)[0]
        recipient_count = struct.unpack_from("<I", data, 16)[0]
        attachment_count = struct.unpack_from("<I", data, 20)[0]
        reserved_1 = data[24:32]
        if (len(data) - 32) % 16 != 0:
            raise MsgError(
                f"Top-level property payload length {len(data) - 32} is not divisible by 16 with 32-byte header."
            )
        header = PropertyStreamHeaderTopLevel(
            reserved_0=reserved_0,
            next_recipient_id=next_recipient_id,
            next_attachment_id=next_attachment_id,
            recipient_count=recipient_count,
            attachment_count=attachment_count,
            reserved_1=reserved_1,
        )
        entries = cls._parse_fixed_length_entries(data[32:], context="top-level")
        return header, entries

    @classmethod
    def parse_subobject_property_stream_data(
        cls, data: bytes
    ) -> Tuple[PropertyStreamHeaderSubobject, List[PropertyEntryFixedLength]]:
        """Decode recipient/attachment property stream header and fixed-length entries."""
        if len(data) < 8:
            raise MsgError("Subobject property stream is smaller than 8-byte header.")
        header = PropertyStreamHeaderSubobject(reserved_0=data[0:8])
        entries = cls._parse_fixed_length_entries(data[8:], context="subobject")
        return header, entries

    @classmethod
    def _parse_fixed_length_entries(cls, payload: bytes, context: str) -> List[PropertyEntryFixedLength]:
        """Read fixed-length property entries that contain property tag, flags, and inline value bytes."""
        if len(payload) % 16 != 0:
            raise MsgError(f"{context} property payload length {len(payload)} is not divisible by 16.")
        entries: List[PropertyEntryFixedLength] = []
        for off in range(0, len(payload), 16):
            property_tag = struct.unpack_from("<I", payload, off)[0]
            flags = struct.unpack_from("<I", payload, off + 4)[0]
            value = payload[off + 8 : off + 16]
            entries.append(PropertyEntryFixedLength(property_tag=property_tag, flags=flags, value=value))
        return entries

    def _build_storage_layout(self) -> StorageLayout:
        children = list(self._cfb.iter_children(ROOT_STREAM_ID))

        named_property_mapping_storages = [
            child for child in children if child.is_storage() and child.name == NAMED_PROPERTY_MAPPING_STORAGE_NAME
        ]
        if len(named_property_mapping_storages) != 1:
            raise MsgError(
                f"Expected exactly one top-level named property mapping storage, found {len(named_property_mapping_storages)}"
            )

        top_level_property_streams = [
            child for child in children if child.is_stream() and child.name == PROPERTY_STREAM_NAME
        ]
        if len(top_level_property_streams) != 1:
            raise MsgError(f"Expected exactly one top-level property stream, found {len(top_level_property_streams)}")

        recipient_storages = [child for child in children if child.is_storage() and self._RECIPIENT_NAME_RE.match(child.name)]
        attachment_storages = [child for child in children if child.is_storage() and self._ATTACHMENT_NAME_RE.match(child.name)]

        for child in children:
            if child.is_storage() and child.name.startswith(RECIPIENT_STORAGE_PREFIX[:-1]) and not self._RECIPIENT_NAME_RE.match(
                child.name
            ):
                raise MsgError(f"Invalid recipient storage naming pattern: {child.name}")
            if child.is_storage() and child.name.startswith(ATTACHMENT_STORAGE_PREFIX[:-1]) and not self._ATTACHMENT_NAME_RE.match(
                child.name
            ):
                raise MsgError(f"Invalid attachment storage naming pattern: {child.name}")

        if len(recipient_storages) > MAX_RECIPIENT_STORAGES:
            raise MsgError(f"Recipient storage count exceeds {MAX_RECIPIENT_STORAGES}.")
        if len(attachment_storages) > MAX_ATTACHMENT_STORAGES:
            raise MsgError(f"Attachment storage count exceeds {MAX_ATTACHMENT_STORAGES}.")

        return StorageLayout(
            recipient_storages=tuple(recipient_storages),
            attachment_storages=tuple(attachment_storages),
            named_property_mapping_storage=named_property_mapping_storages[0],
            top_level_property_stream=top_level_property_streams[0],
        )

    def _validate_top_level_counts(self) -> None:
        if len(self._layout.recipient_storages) != self.top_level_header.recipient_count:
            message = (
                f"Recipient storage count mismatch: {len(self._layout.recipient_storages)} != "
                f"{self.top_level_header.recipient_count}"
            )
            if self._strict:
                raise MsgError(message)
            self._validation_issues.append(message)
        if len(self._layout.attachment_storages) != self.top_level_header.attachment_count:
            message = (
                f"Attachment storage count mismatch: {len(self._layout.attachment_storages)} != "
                f"{self.top_level_header.attachment_count}"
            )
            if self._strict:
                raise MsgError(message)
            self._validation_issues.append(message)

    def _validate_embedded_message_rules(self) -> None:
        for attachment in self._layout.attachment_storages:
            embedded_storage = self._cfb.find_child_by_name(attachment.stream_id, EMBEDDED_MESSAGE_STORAGE_NAME)
            if embedded_storage is None:
                continue
            if not embedded_storage.is_storage():
                raise MsgError("Embedded message entry exists but is not a storage object.")

            embedded_nameid = self._cfb.find_child_by_name(
                embedded_storage.stream_id, NAMED_PROPERTY_MAPPING_STORAGE_NAME
            )
            # Interop: some producers include a nameid mapping storage in embedded messages.
            # We keep parsing instead of rejecting the whole MSG file.
            if embedded_nameid is not None and not embedded_nameid.is_storage():
                raise MsgError("Embedded named property mapping entry exists but is not a storage object.")

    def _get_single_property_stream_entry(self, storage_stream_id: int) -> DirectoryEntry:
        property_streams = [
            child
            for child in self._cfb.iter_children(storage_stream_id)
            if child.is_stream() and child.name == PROPERTY_STREAM_NAME
        ]
        if len(property_streams) != 1:
            raise MsgError(f"Expected one property stream in storage sid={storage_stream_id}, found {len(property_streams)}")
        return property_streams[0]
