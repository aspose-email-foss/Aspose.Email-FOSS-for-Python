from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..cfb import CFBDocument, CFBReader, CFBStorage, CFBStream, CFBWriter, DirectoryEntry, ROOT_STREAM_ID

from .property_tags import CommonMessagePropertyId
from .property_types import PropertyTypeCode
from .reader import MsgError, MsgReader
from .types import (
    ATTACHMENT_STORAGE_PREFIX,
    EMBEDDED_MESSAGE_STORAGE_NAME,
    NAMED_PROPERTY_MAPPING_STORAGE_NAME,
    PROPERTY_STREAM_NAME,
    RECIPIENT_STORAGE_PREFIX,
    PropertyEntryFixedLength,
    PropertyStreamHeaderSubobject,
    PropertyStreamHeaderTopLevel,
)


MESSAGE_ROLE = "message"
RECIPIENT_ROLE = "recipient"
ATTACHMENT_ROLE = "attachment"
EMBEDDED_MESSAGE_ROLE = "embedded_message"
NAMED_PROPERTY_MAPPING_ROLE = "named_property_mapping"
CUSTOM_ATTACHMENT_ROLE = "custom_attachment"
GENERIC_ROLE = "generic"

_MESSAGE_CONTAINER_ROLES = {MESSAGE_ROLE, EMBEDDED_MESSAGE_ROLE}
_PROPERTY_STREAM_ROLES = {MESSAGE_ROLE, EMBEDDED_MESSAGE_ROLE, RECIPIENT_ROLE, ATTACHMENT_ROLE}
_RECIPIENT_NAME_RE = re.compile(r"^__recip_version1\.0_#[0-9A-Fa-f]{8}$")
_ATTACHMENT_NAME_RE = re.compile(r"^__attach_version1\.0_#[0-9A-Fa-f]{8}$")


@dataclass
class MsgStream:
    """Mutable MSG stream node with raw bytes and CFB metadata."""

    name: str
    data: bytes = b""
    clsid: bytes = b"\x00" * 16
    state_bits: int = 0
    creation_time: int = 0
    modified_time: int = 0


@dataclass
class MsgStorage:
    """Mutable MSG storage node with role classification and parsed property-stream metadata."""

    name: str
    role: str = GENERIC_ROLE
    clsid: bytes = b"\x00" * 16
    state_bits: int = 0
    creation_time: int = 0
    modified_time: int = 0
    streams: list[MsgStream] = field(default_factory=list)
    storages: list["MsgStorage"] = field(default_factory=list)
    property_header_kind: str | None = None
    property_stream_header: PropertyStreamHeaderTopLevel | PropertyStreamHeaderSubobject | None = None
    fixed_length_properties: tuple[PropertyEntryFixedLength, ...] = ()
    property_stream_parse_error: str | None = None

    def add_stream(self, stream: MsgStream) -> MsgStream:
        self.streams.append(stream)
        return stream

    def add_storage(self, storage: "MsgStorage") -> "MsgStorage":
        self.storages.append(storage)
        return storage

    def iter_streams(self) -> Iterator[MsgStream]:
        for stream in self.streams:
            yield stream

    def iter_storages(self) -> Iterator["MsgStorage"]:
        for storage in self.storages:
            yield storage

    def find_stream(self, name: str) -> MsgStream | None:
        for stream in self.streams:
            if stream.name == name:
                return stream
        return None

    def find_storage(self, name: str) -> "MsgStorage" | None:
        for storage in self.storages:
            if storage.name == name:
                return storage
        return None


@dataclass
class MsgDocument:
    """Mutable MSG document model that can be serialized through the CFB writer."""

    root: MsgStorage
    major_version: int = 3
    minor_version: int = 0x003E
    transaction_signature_number: int = 0
    strict: bool = False

    @classmethod
    def from_reader(cls, reader: MsgReader) -> "MsgDocument":
        cfb = reader.cfb_reader

        def build_storage(entry: DirectoryEntry, role: str) -> MsgStorage:
            storage = MsgStorage(
                name=entry.name,
                role=role,
                clsid=bytes(entry.clsid),
                state_bits=entry.state_bits,
                creation_time=int(entry.creation_time),
                modified_time=int(entry.modified_time),
            )

            if role in _PROPERTY_STREAM_ROLES:
                try:
                    header_kind, header, entries = _parse_property_stream(reader, entry.stream_id, role)
                except MsgError as exc:
                    if role == MESSAGE_ROLE and entry.stream_id == ROOT_STREAM_ID:
                        raise
                    storage.property_stream_parse_error = str(exc)
                else:
                    storage.property_header_kind = header_kind
                    storage.property_stream_header = header
                    storage.fixed_length_properties = tuple(entries)

            attach_method = _extract_attach_method(storage.fixed_length_properties) if role == ATTACHMENT_ROLE else None
            for child in cfb.iter_children(entry.stream_id):
                if child.is_stream():
                    storage.streams.append(
                        MsgStream(
                            name=child.name,
                            data=cfb.get_stream_data(child.stream_id),
                            clsid=bytes(child.clsid),
                            state_bits=child.state_bits,
                            creation_time=int(child.creation_time),
                            modified_time=int(child.modified_time),
                        )
                    )
                    continue
                child_role = _classify_storage_role(cfb, role, child, attach_method)
                storage.storages.append(build_storage(child, child_role))
            return storage

        root_entry = cfb.get_entry(ROOT_STREAM_ID)
        return cls(
            root=build_storage(root_entry, MESSAGE_ROLE),
            major_version=cfb.header.major_version,
            minor_version=cfb.header.minor_version,
            transaction_signature_number=cfb.header.transaction_signature_number,
            strict=reader.strict,
        )

    @classmethod
    def from_file(cls, path: Path | str, *, strict: bool = False) -> "MsgDocument":
        with MsgReader.from_file(path, strict=strict) as reader:
            return cls.from_reader(reader)

    def to_cfb_document(self) -> CFBDocument:
        _validate_msg_storage(self.root, is_root=True, strict=self.strict)
        return CFBDocument(
            root=_to_cfb_storage(self.root),
            major_version=self.major_version,
            minor_version=self.minor_version,
            transaction_signature_number=self.transaction_signature_number,
        )


class MsgWriter:
    """Serializer that writes a MsgDocument into a CFB-backed .msg payload."""

    @classmethod
    def to_bytes(cls, document: MsgDocument) -> bytes:
        return CFBWriter.to_bytes(document.to_cfb_document())

    @classmethod
    def write_file(cls, document: MsgDocument, path: Path | str) -> None:
        Path(path).write_bytes(cls.to_bytes(document))


def _parse_property_stream(
    reader: MsgReader,
    storage_stream_id: int,
    role: str,
) -> tuple[str, PropertyStreamHeaderTopLevel | PropertyStreamHeaderSubobject, list[PropertyEntryFixedLength]]:
    if role in _MESSAGE_CONTAINER_ROLES:
        header, entries = reader.parse_message_property_stream(storage_stream_id)
        return ("message", header, entries)
    header, entries = reader.parse_subobject_property_stream(storage_stream_id)
    return ("subobject", header, entries)


def _classify_storage_role(
    cfb: CFBReader,
    parent_role: str,
    child: DirectoryEntry,
    attach_method: int | None,
) -> str:
    if parent_role in _MESSAGE_CONTAINER_ROLES:
        if child.name == NAMED_PROPERTY_MAPPING_STORAGE_NAME:
            return NAMED_PROPERTY_MAPPING_ROLE
        if _RECIPIENT_NAME_RE.match(child.name):
            return RECIPIENT_ROLE
        if _ATTACHMENT_NAME_RE.match(child.name):
            return ATTACHMENT_ROLE
        return GENERIC_ROLE

    if parent_role == ATTACHMENT_ROLE and child.name == EMBEDDED_MESSAGE_STORAGE_NAME:
        if attach_method == 0x00000005:
            return EMBEDDED_MESSAGE_ROLE
        if attach_method == 0x00000006:
            return CUSTOM_ATTACHMENT_ROLE
        if cfb.find_child_by_name(child.stream_id, PROPERTY_STREAM_NAME) is not None:
            return EMBEDDED_MESSAGE_ROLE
        return CUSTOM_ATTACHMENT_ROLE

    return GENERIC_ROLE


def _extract_attach_method(entries: tuple[PropertyEntryFixedLength, ...]) -> int | None:
    target_tag = (int(CommonMessagePropertyId.ATTACH_METHOD) << 16) | int(PropertyTypeCode.PTYP_INTEGER32)
    for entry in entries:
        if entry.property_tag != target_tag:
            continue
        return struct.unpack_from("<I", entry.value, 0)[0]
    return None


def _validate_msg_storage(storage: MsgStorage, *, is_root: bool, strict: bool) -> None:
    property_stream_count = sum(1 for stream in storage.streams if stream.name == PROPERTY_STREAM_NAME)
    if storage.role in _PROPERTY_STREAM_ROLES and property_stream_count != 1:
        raise MsgError(
            f"Storage {storage.name!r} with role {storage.role!r} must contain exactly one property stream; found {property_stream_count}"
        )

    if storage.role == MESSAGE_ROLE and is_root:
        named_mapping_count = sum(1 for child in storage.storages if child.name == NAMED_PROPERTY_MAPPING_STORAGE_NAME)
        if named_mapping_count != 1:
            raise MsgError(f"Top-level MSG storage must contain exactly one named property mapping storage; found {named_mapping_count}")
    if storage.role == RECIPIENT_ROLE and not _RECIPIENT_NAME_RE.match(storage.name):
        raise MsgError(f"Invalid recipient storage name: {storage.name}")
    if storage.role == ATTACHMENT_ROLE and not _ATTACHMENT_NAME_RE.match(storage.name):
        raise MsgError(f"Invalid attachment storage name: {storage.name}")
    if strict and storage.role == EMBEDDED_MESSAGE_ROLE:
        named_mapping_count = sum(1 for child in storage.storages if child.name == NAMED_PROPERTY_MAPPING_STORAGE_NAME)
        if named_mapping_count != 0:
            raise MsgError("Embedded message storage must not contain a named property mapping storage in strict mode.")

    for child in storage.storages:
        _validate_msg_storage(child, is_root=False, strict=strict)


def _to_cfb_storage(storage: MsgStorage) -> CFBStorage:
    cfb_storage = CFBStorage(
        name=storage.name,
        clsid=storage.clsid,
        state_bits=storage.state_bits,
        creation_time=storage.creation_time,
        modified_time=storage.modified_time,
    )
    for stream in storage.streams:
        cfb_storage.add_stream(
            CFBStream(
                name=stream.name,
                data=stream.data,
                clsid=stream.clsid,
                state_bits=stream.state_bits,
                creation_time=stream.creation_time,
                modified_time=stream.modified_time,
            )
        )
    for child in storage.storages:
        cfb_storage.add_storage(_to_cfb_storage(child))
    return cfb_storage


def hash_payload(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
