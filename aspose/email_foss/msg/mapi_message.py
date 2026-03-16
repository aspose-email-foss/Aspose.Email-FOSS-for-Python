from __future__ import annotations

import binascii
import mimetypes
import re
import struct
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser, Parser
from email.utils import format_datetime, formataddr, getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from .property_id import PropertyId
from .property_tags import CommonMessagePropertyId
from .property_types import PropertyTypeCode
from .reader import MsgError, MsgReader
from .types import (
    ATTACHMENT_STORAGE_PREFIX,
    EMBEDDED_MESSAGE_STORAGE_NAME,
    NAMED_PROPERTY_MAPPING_STORAGE_NAME,
    PROPERTY_STREAM_NAME,
    PROPERTY_VALUE_STREAM_PREFIX,
    PROPATTR_READABLE,
    PROPATTR_WRITABLE,
    RECIPIENT_STORAGE_PREFIX,
)
from .writer import (
    ATTACHMENT_ROLE,
    CUSTOM_ATTACHMENT_ROLE,
    EMBEDDED_MESSAGE_ROLE,
    MESSAGE_ROLE,
    MsgDocument,
    MsgStorage,
    MsgStream,
    MsgWriter,
    NAMED_PROPERTY_MAPPING_ROLE,
    RECIPIENT_ROLE,
)


PS_MAPI = uuid.UUID("00020328-0000-0000-c000-000000000046")
PS_PUBLIC_STRINGS = uuid.UUID("00020329-0000-0000-c000-000000000046")
STORE_UNICODE_OK = 0x00040000
DEFAULT_PROPERTY_FLAGS = PROPATTR_READABLE | PROPATTR_WRITABLE

RECIPIENT_TYPE_TO = 1
RECIPIENT_TYPE_CC = 2
RECIPIENT_TYPE_BCC = 3

RECIPIENT_TYPE_PROPERTY_ID = 0x0C15
ROWID_PROPERTY_ID = 0x3000
DISPLAY_NAME_PROPERTY_ID = 0x3001
ADDRESS_TYPE_PROPERTY_ID = 0x3002
EMAIL_ADDRESS_PROPERTY_ID = 0x3003
SMTP_ADDRESS_PROPERTY_ID = 0x39FE
SEARCH_KEY_PROPERTY_ID = 0x300B
INSTANCE_KEY_PROPERTY_ID = 0x0FF6
RECIPIENT_ENTRY_ID_PROPERTY_ID = 0x0FFF
ACCESS_PROPERTY_ID = 0x0FF4
ACCESS_LEVEL_PROPERTY_ID = 0x0FF7
RECORD_KEY_PROPERTY_ID = 0x0FF9
SENDER_ENTRY_ID_PROPERTY_ID = 0x0C19
SENDER_SEARCH_KEY_PROPERTY_ID = 0x0C1D
SENT_REPRESENTING_SEARCH_KEY_PROPERTY_ID = 0x003B
SENT_REPRESENTING_ENTRY_ID_PROPERTY_ID = 0x0041
SENT_REPRESENTING_NAME_PROPERTY_ID = 0x0042
SENT_REPRESENTING_ADDRESS_TYPE_PROPERTY_ID = 0x0064
SENT_REPRESENTING_EMAIL_ADDRESS_PROPERTY_ID = 0x0065
IMPORTANCE_PROPERTY_ID = 0x0017
SENSITIVITY_PROPERTY_ID = 0x0036
CLIENT_SUBMIT_TIME_PROPERTY_ID = 0x0039
CONVERSATION_TOPIC_PROPERTY_ID = 0x0070
CONVERSATION_INDEX_PROPERTY_ID = 0x0071
CONVERSATION_INDEX_TRACKING_PROPERTY_ID = 0x3016
NORMALIZED_SUBJECT_PROPERTY_ID = 0x0E1D
DEFAULT_MESSAGE_CLASS = "IPM.Note"
DEFAULT_SMTP_ADDRESS_TYPE = "SMTP"
DEFAULT_INTERNET_CODEPAGE_ASCII = 20127
DEFAULT_INTERNET_CODEPAGE = 65001
DEFAULT_IMPORTANCE = 1
DEFAULT_SENSITIVITY = 0
MESSAGE_FLAG_READ = 0x00000001
MESSAGE_FLAG_UNSENT = 0x00000008
MESSAGE_FLAG_HASATTACH = 0x00000010
DEFAULT_ACCESS = 2
DEFAULT_ACCESS_LEVEL = 0
DEFAULT_ATTACH_TAG = bytes.fromhex("2A864886F714030A04")
_MISSING = object()

ATTACH_LONG_PATHNAME_PROPERTY_ID = 0x370D
ATTACH_EXTENSION_PROPERTY_ID = 0x3703
ATTACH_SIZE_PROPERTY_ID = 0x0E20
ATTACH_NUM_PROPERTY_ID = 0x0E21

ATTACH_METHOD_BY_VALUE = 1
ATTACH_METHOD_EMBEDDED = 5
ATTACH_METHOD_STORAGE = 6

_STREAM_PROP_RE = re.compile(rf"^{re.escape(PROPERTY_VALUE_STREAM_PREFIX)}([0-9A-Fa-f]{{4}})([0-9A-Fa-f]{{4}})$")
_STREAM_PROP_INDEXED_RE = re.compile(
    rf"^{re.escape(PROPERTY_VALUE_STREAM_PREFIX)}([0-9A-Fa-f]{{4}})([0-9A-Fa-f]{{4}})-([0-9A-Fa-f]{{8}})$"
)

_FIXED_INLINE_SIZES: dict[int, int] = {
    int(PropertyTypeCode.PTYP_INTEGER16): 2,
    int(PropertyTypeCode.PTYP_INTEGER32): 4,
    int(PropertyTypeCode.PTYP_FLOATING32): 4,
    int(PropertyTypeCode.PTYP_FLOATING64): 8,
    int(PropertyTypeCode.PTYP_CURRENCY): 8,
    int(PropertyTypeCode.PTYP_FLOATINGTIME): 8,
    int(PropertyTypeCode.PTYP_ERRORCODE): 4,
    int(PropertyTypeCode.PTYP_BOOLEAN): 2,
    int(PropertyTypeCode.PTYP_INTEGER64): 8,
    int(PropertyTypeCode.PTYP_TIME): 8,
}
_MULTI_FIXED_BASE_TYPES: dict[int, int] = {
    int(PropertyTypeCode.PTYP_MULTIPLE_INTEGER16): int(PropertyTypeCode.PTYP_INTEGER16),
    int(PropertyTypeCode.PTYP_MULTIPLE_INTEGER32): int(PropertyTypeCode.PTYP_INTEGER32),
    int(PropertyTypeCode.PTYP_MULTIPLE_FLOATING32): int(PropertyTypeCode.PTYP_FLOATING32),
    int(PropertyTypeCode.PTYP_MULTIPLE_FLOATING64): int(PropertyTypeCode.PTYP_FLOATING64),
    int(PropertyTypeCode.PTYP_MULTIPLE_CURRENCY): int(PropertyTypeCode.PTYP_CURRENCY),
    int(PropertyTypeCode.PTYP_MULTIPLE_FLOATINGTIME): int(PropertyTypeCode.PTYP_FLOATINGTIME),
    int(PropertyTypeCode.PTYP_MULTIPLE_INTEGER64): int(PropertyTypeCode.PTYP_INTEGER64),
    int(PropertyTypeCode.PTYP_MULTIPLE_TIME): int(PropertyTypeCode.PTYP_TIME),
    int(PropertyTypeCode.PTYP_MULTIPLE_GUID): int(PropertyTypeCode.PTYP_GUID),
}
_MULTI_VARIABLE_BASE_TYPES: dict[int, int] = {
    int(PropertyTypeCode.PTYP_MULTIPLE_STRING8): int(PropertyTypeCode.PTYP_STRING8),
    int(PropertyTypeCode.PTYP_MULTIPLE_STRING): int(PropertyTypeCode.PTYP_STRING),
    int(PropertyTypeCode.PTYP_MULTIPLE_BINARY): int(PropertyTypeCode.PTYP_BINARY),
}


@dataclass(frozen=True)
class MapiNamedProperty:
    """Identifier for a named MAPI property."""

    property_set: uuid.UUID
    kind: str
    name: str | None = None
    lid: int | None = None
    property_id: int | None = None

    @classmethod
    def string(cls, name: str, property_set: uuid.UUID | str = PS_PUBLIC_STRINGS) -> "MapiNamedProperty":
        return cls(property_set=_coerce_uuid(property_set), kind="string", name=name)

    @classmethod
    def numeric(cls, lid: int, property_set: uuid.UUID | str) -> "MapiNamedProperty":
        return cls(property_set=_coerce_uuid(property_set), kind="numeric", lid=lid)


@dataclass
class MapiProperty:
    """Logical MAPI property with optional named-property identity."""

    property_id: int
    property_type: int
    value: Any
    flags: int = DEFAULT_PROPERTY_FLAGS
    named: MapiNamedProperty | None = None
    raw_inline_value: bytes | None = None
    raw_size_value: int | None = None
    raw_reserved_value: int | None = None
    raw_direct_stream: bytes | None = None
    raw_indexed_streams: tuple[tuple[int, bytes], ...] = ()
    preserve_raw: bool = False

    @property
    def property_tag(self) -> int:
        return (self.property_id << 16) | self.property_type

    def clone(self) -> "MapiProperty":
        return replace(self)

    def clear_raw(self) -> None:
        self.raw_inline_value = None
        self.raw_size_value = None
        self.raw_reserved_value = None
        self.raw_direct_stream = None
        self.raw_indexed_streams = ()
        self.preserve_raw = False


class MapiPropertyCollection:
    def __init__(self) -> None:
        self._properties: dict[tuple[int, int], MapiProperty] = {}

    def set(self, property: MapiProperty) -> MapiProperty:
        self._properties[(property.property_id, property.property_type)] = property
        return property

    def add(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type: int | PropertyTypeCode,
        value: Any,
        *,
        flags: int = DEFAULT_PROPERTY_FLAGS,
        named: MapiNamedProperty | None = None,
    ) -> MapiProperty:
        property_id = int(property_id)
        key = (property_id, int(property_type))
        existing = self._properties.get(key)
        if existing is not None and existing.value == value and existing.flags == flags and existing.named == named:
            return existing
        return self.set(
            MapiProperty(
                property_id=property_id,
                property_type=int(property_type),
                value=value,
                flags=flags,
                named=named,
            )
        )

    def get(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type: int | None = None,
    ) -> MapiProperty | None:
        property_key = property_id
        property_id = int(property_id)
        if property_type is not None:
            return self._properties.get((property_id, int(property_type)))
        if isinstance(property_key, PropertyId):
            preferred = self._properties.get((property_id, property_key.property_type))
            if preferred is not None:
                return preferred
        matches = [prop for (pid, _), prop in self._properties.items() if pid == property_id]
        if not matches:
            return None
        return sorted(matches, key=lambda item: item.property_type)[0]

    def remove(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type: int | None = None,
    ) -> None:
        property_type = _resolve_property_type(property_id, property_type)
        property_id = int(property_id)
        if property_type is not None:
            self._properties.pop((property_id, int(property_type)), None)
            return
        for key in [key for key in self._properties if key[0] == property_id]:
            self._properties.pop(key, None)

    def iter_properties(self) -> Iterator[MapiProperty]:
        for key in sorted(self._properties):
            yield self._properties[key]


@dataclass
class MapiRecipient:
    """Mutable recipient object."""

    display_name: str | None = None
    email_address: str | None = None
    recipient_type: int = RECIPIENT_TYPE_TO
    address_type: str = "SMTP"
    storage_id: int | None = None
    properties: MapiPropertyCollection = field(default_factory=MapiPropertyCollection)
    extra_streams: list[MsgStream] = field(default_factory=list)
    extra_storages: list[MsgStorage] = field(default_factory=list)
    header_reserved_0: bytes = b"\x00" * 8

    def set_property(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type_or_value: int | PropertyTypeCode | Any,
        value: Any = _MISSING,
        *,
        flags: int = DEFAULT_PROPERTY_FLAGS,
    ) -> MapiProperty:
        property_type, resolved_value = _resolve_set_property_args(property_id, property_type_or_value, value)
        return self.properties.add(property_id, property_type, resolved_value, flags=flags)


@dataclass
class MapiAttachment:
    """Mutable attachment object."""

    filename: str | None = None
    data: bytes = b""
    mime_type: str | None = None
    content_id: str | None = None
    attach_method: int = ATTACH_METHOD_BY_VALUE
    storage_id: int | None = None
    embedded_message: "MapiMessage | None" = None
    custom_storage: MsgStorage | None = None
    properties: MapiPropertyCollection = field(default_factory=MapiPropertyCollection)
    extra_streams: list[MsgStream] = field(default_factory=list)
    header_reserved_0: bytes = b"\x00" * 8

    @property
    def storage_name(self) -> str | None:
        if self.storage_id is None:
            return None
        return f"{ATTACHMENT_STORAGE_PREFIX}{self.storage_id:08X}"

    @property
    def is_embedded_message(self) -> bool:
        return self.embedded_message is not None or self.attach_method == ATTACH_METHOD_EMBEDDED

    @property
    def is_storage_attachment(self) -> bool:
        return self.custom_storage is not None or self.attach_method == ATTACH_METHOD_STORAGE

    @property
    def embedded_storage_name(self) -> str | None:
        if self.is_embedded_message or self.is_storage_attachment:
            return EMBEDDED_MESSAGE_STORAGE_NAME
        return None

    @classmethod
    def from_bytes(
        cls,
        filename: str,
        data: bytes,
        *,
        mime_type: str | None = None,
        content_id: str | None = None,
    ) -> "MapiAttachment":
        return cls(filename=filename, data=data, mime_type=mime_type, content_id=content_id)

    @classmethod
    def from_embedded_message(
        cls,
        message: "MapiMessage",
        *,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> "MapiAttachment":
        return cls(
            filename=filename or f"{message.subject or 'message'}.msg",
            mime_type=mime_type or "message/rfc822",
            attach_method=ATTACH_METHOD_EMBEDDED,
            embedded_message=message,
        )

    def set_property(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type_or_value: int | PropertyTypeCode | Any,
        value: Any = _MISSING,
        *,
        flags: int = DEFAULT_PROPERTY_FLAGS,
    ) -> MapiProperty:
        property_type, resolved_value = _resolve_set_property_args(property_id, property_type_or_value, value)
        return self.properties.add(property_id, property_type, resolved_value, flags=flags)


@dataclass
class _NamedPropertyDefinition:
    identity: MapiNamedProperty
    property_id: int
    guid_index: int | None = None


class _NamedPropertyMapping:
    def __init__(self) -> None:
        self._definitions_by_key: dict[tuple[uuid.UUID, str, str | int], _NamedPropertyDefinition] = {}
        self._definitions_by_id: dict[int, _NamedPropertyDefinition] = {}

    @classmethod
    def from_storage(cls, storage: MsgStorage | None) -> "_NamedPropertyMapping":
        mapping = cls()
        if storage is None:
            return mapping
        guid_stream = storage.find_stream("__substg1.0_00020102")
        entry_stream = storage.find_stream("__substg1.0_00030102")
        string_stream = storage.find_stream("__substg1.0_00040102")
        if entry_stream is None:
            return mapping

        guid_list = []
        if guid_stream is not None:
            guid_list = [
                uuid.UUID(bytes_le=guid_stream.data[offset : offset + 16])
                for offset in range(0, len(guid_stream.data), 16)
                if len(guid_stream.data[offset : offset + 16]) == 16
            ]
        names_by_offset = _parse_nameid_string_stream(string_stream.data if string_stream is not None else b"")

        for offset in range(0, len(entry_stream.data), 8):
            first, index_and_kind = struct.unpack_from("<II", entry_stream.data, offset)
            property_index = (index_and_kind >> 16) & 0xFFFF
            guid_index = (index_and_kind >> 1) & 0x7FFF
            kind_bit = index_and_kind & 0x1
            property_id = 0x8000 + property_index
            property_set = _guid_from_index(guid_index, guid_list)
            if kind_bit == 0:
                identity = MapiNamedProperty.numeric(first, property_set)
            else:
                identity = MapiNamedProperty.string(names_by_offset.get(first, ""), property_set)
            mapping._register(identity, property_id, guid_index=guid_index)
        return mapping

    def get_by_property_id(self, property_id: int) -> MapiNamedProperty | None:
        definition = self._definitions_by_id.get(property_id)
        return definition.identity if definition is not None else None

    def ensure(self, identity: MapiNamedProperty, *, preferred_property_id: int | None = None) -> MapiNamedProperty:
        key = _named_property_key(identity)
        if key in self._definitions_by_key:
            definition = self._definitions_by_key[key]
            return replace(definition.identity, property_id=definition.property_id)
        property_id = preferred_property_id if preferred_property_id is not None else max(self._definitions_by_id.keys(), default=0x7FFF) + 1
        return self._register(identity, property_id).identity

    def iter_definitions(self) -> Iterator[_NamedPropertyDefinition]:
        for property_id in sorted(self._definitions_by_id):
            yield self._definitions_by_id[property_id]

    def _register(
        self,
        identity: MapiNamedProperty,
        property_id: int,
        *,
        guid_index: int | None = None,
    ) -> _NamedPropertyDefinition:
        normalized = replace(identity, property_set=_coerce_uuid(identity.property_set), property_id=property_id)
        definition = _NamedPropertyDefinition(identity=normalized, property_id=property_id, guid_index=guid_index)
        self._definitions_by_key[_named_property_key(normalized)] = definition
        self._definitions_by_id[property_id] = definition
        return definition

    def to_storage(self) -> MsgStorage:
        storage = MsgStorage(name=NAMED_PROPERTY_MAPPING_STORAGE_NAME, role=NAMED_PROPERTY_MAPPING_ROLE)
        guid_list: list[uuid.UUID] = []
        guid_positions: dict[uuid.UUID, int] = {}
        string_offsets: dict[int, int] = {}
        string_stream = bytearray()
        entry_stream = bytearray()
        mapping_streams: dict[str, bytearray] = {}

        for definition in self.iter_definitions():
            property_set = definition.identity.property_set
            if property_set == PS_MAPI:
                guid_index = 1
            elif property_set == PS_PUBLIC_STRINGS:
                guid_index = 2
            else:
                if property_set not in guid_positions:
                    guid_positions[property_set] = len(guid_list)
                    guid_list.append(property_set)
                guid_index = guid_positions[property_set] + 3

            property_index = definition.property_id - 0x8000
            if definition.identity.kind == "numeric":
                name_or_offset = int(definition.identity.lid or 0)
                kind_bit = 0
                stream_hash_input = name_or_offset
            else:
                if property_index not in string_offsets:
                    string_offsets[property_index] = len(string_stream)
                    encoded = (definition.identity.name or "").encode("utf-16-le")
                    string_stream.extend(struct.pack("<I", len(encoded)))
                    string_stream.extend(encoded)
                    while len(string_stream) % 4:
                        string_stream.append(0)
                name_or_offset = string_offsets[property_index]
                kind_bit = 1
                stream_hash_input = _crc32_utf16(definition.identity.name or "")

            index_and_kind = (property_index << 16) | (guid_index << 1) | kind_bit
            entry_stream.extend(struct.pack("<II", name_or_offset, index_and_kind))

            stream_id = _mapping_stream_id(stream_hash_input, guid_index, kind_bit)
            stream_name = f"{PROPERTY_VALUE_STREAM_PREFIX}{((stream_id << 16) | 0x0102):08X}"
            mapping_streams.setdefault(stream_name, bytearray()).extend(struct.pack("<II", stream_hash_input, index_and_kind))

        storage.add_stream(MsgStream("__substg1.0_00020102", b"".join(guid.bytes_le for guid in guid_list)))
        storage.add_stream(MsgStream("__substg1.0_00030102", bytes(entry_stream)))
        storage.add_stream(MsgStream("__substg1.0_00040102", bytes(string_stream)))
        for stream_name in sorted(mapping_streams):
            storage.add_stream(MsgStream(stream_name, bytes(mapping_streams[stream_name])))
        return storage


@dataclass
class MapiMessage:
    """Mutable high-level MSG object with MSG and EmailMessage conversion support."""

    _SKIP_IMPORTED_HEADERS = {
        "content-type",
        "content-transfer-encoding",
        "content-disposition",
        "content-id",
        "content-description",
        "content-language",
        "content-location",
        "mime-version",
    }
    _TRANSPORT_HEADER_EXCLUDE = {
        "subject",
        "to",
        "cc",
        "bcc",
        "message-id",
        "from",
        "date",
        "content-type",
        "content-transfer-encoding",
        "content-disposition",
        "content-id",
        "content-description",
        "content-language",
        "content-location",
        "mime-version",
    }
    _KNOWN_MIME_MAINTYPES = {
        "application",
        "audio",
        "font",
        "image",
        "message",
        "model",
        "text",
        "video",
    }
    _PREFERRED_PROPERTY_TYPES = (
        PropertyTypeCode.PTYP_STRING,
        PropertyTypeCode.PTYP_STRING8,
        PropertyTypeCode.PTYP_BINARY,
        PropertyTypeCode.PTYP_TIME,
        PropertyTypeCode.PTYP_INTEGER32,
        PropertyTypeCode.PTYP_INTEGER64,
        PropertyTypeCode.PTYP_INTEGER16,
        PropertyTypeCode.PTYP_BOOLEAN,
    )
    _CODEPAGE_PROPERTY_IDS = (
        0x3FFD,
        0x3FDE,
    )
    _STREAM_PROP_RE = _STREAM_PROP_RE
    _STREAM_PROP_INDEXED_RE = _STREAM_PROP_INDEXED_RE

    unicode_strings: bool = True
    properties: MapiPropertyCollection = field(default_factory=MapiPropertyCollection)
    recipients: list[MapiRecipient] = field(default_factory=list)
    attachments: list[MapiAttachment] = field(default_factory=list)
    extra_streams: list[MsgStream] = field(default_factory=list)
    extra_storages: list[MsgStorage] = field(default_factory=list)
    nameid_mapping: _NamedPropertyMapping = field(default_factory=_NamedPropertyMapping)
    major_version: int = 3
    minor_version: int = 0x003E
    transaction_signature_number: int = 0
    header_reserved_0: bytes = b"\x00" * 8
    header_reserved_1: bytes = b"\x00" * 8
    emit_store_support_mask: bool = True
    emit_compatibility_defaults: bool = True
    preserve_declared_header_counts: bool = False
    declared_next_recipient_id: int | None = None
    declared_next_attachment_id: int | None = None
    declared_recipient_count: int | None = None
    declared_attachment_count: int | None = None
    _msg_reader: MsgReader | None = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _validation_issues: tuple[str, ...] = field(default_factory=tuple, init=False, repr=False)

    @classmethod
    def from_file(cls, path: Path | str, *, strict: bool = False) -> "MapiMessage":
        with MsgReader.from_file(path, strict=strict) as reader:
            document = MsgDocument.from_reader(reader)
            message = cls.from_msg_document(document)
            message._validation_issues = tuple(reader.validation_issues)
            return message

    @classmethod
    def from_msg_document(cls, document: MsgDocument) -> "MapiMessage":
        root = document.root
        nameid_storage = root.find_storage(NAMED_PROPERTY_MAPPING_STORAGE_NAME)
        mapping = _NamedPropertyMapping.from_storage(nameid_storage)
        unicode_strings = _detect_unicode_state(root)
        properties, extra_streams, header_0, header_1 = _parse_property_storage(
            root,
            mapping,
            role=MESSAGE_ROLE,
            unicode_strings=unicode_strings,
        )
        message = cls(
            unicode_strings=unicode_strings,
            properties=properties,
            extra_streams=extra_streams,
            extra_storages=[
                _clone_msg_storage(storage)
                for storage in root.storages
                if storage.role not in {NAMED_PROPERTY_MAPPING_ROLE, RECIPIENT_ROLE, ATTACHMENT_ROLE}
            ],
            nameid_mapping=mapping,
            major_version=document.major_version,
            minor_version=document.minor_version,
            transaction_signature_number=document.transaction_signature_number,
            header_reserved_0=header_0,
            header_reserved_1=header_1,
            emit_store_support_mask=properties.get(int(CommonMessagePropertyId.STORE_SUPPORT_MASK), int(PropertyTypeCode.PTYP_INTEGER32)) is not None,
            emit_compatibility_defaults=False,
        )
        header = root.property_stream_header
        if header is not None and hasattr(header, "recipient_count"):
            message.preserve_declared_header_counts = True
            message.declared_next_recipient_id = int(header.next_recipient_id)
            message.declared_next_attachment_id = int(header.next_attachment_id)
            message.declared_recipient_count = int(header.recipient_count)
            message.declared_attachment_count = int(header.attachment_count)
        for storage in root.storages:
            if storage.role == RECIPIENT_ROLE:
                message.recipients.append(_recipient_from_storage(storage, mapping, unicode_strings))
            elif storage.role == ATTACHMENT_ROLE:
                message.attachments.append(_attachment_from_storage(storage, mapping, unicode_strings))
        return message

    @classmethod
    def from_email_message(cls, email_message: EmailMessage, *, unicode_strings: bool = True) -> "MapiMessage":
        message = cls(unicode_strings=unicode_strings)

        subject = email_message.get("Subject")
        if subject:
            message.subject = str(subject)

        message_id = email_message.get("Message-ID")
        if message_id:
            message._set_string_property(int(CommonMessagePropertyId.INTERNET_MESSAGE_ID), str(message_id))

        from_name, from_address = parseaddr(str(email_message.get("From", "")))
        if from_name:
            message._set_string_property(int(CommonMessagePropertyId.SENDER_NAME), from_name)
        if from_address:
            message._set_string_property(int(CommonMessagePropertyId.SENDER_EMAIL_ADDRESS), from_address)

        date_value = email_message.get("Date")
        if date_value:
            try:
                delivery_time = parsedate_to_datetime(str(date_value))
            except (TypeError, ValueError, IndexError):
                delivery_time = None
            if delivery_time is not None:
                if delivery_time.tzinfo is None:
                    delivery_time = delivery_time.replace(tzinfo=UTC)
                else:
                    delivery_time = delivery_time.astimezone(UTC)
                message.set_property(
                    int(CommonMessagePropertyId.MESSAGE_DELIVERY_TIME),
                    PropertyTypeCode.PTYP_TIME,
                    delivery_time,
                )

        for header_name, recipient_type in (
            ("To", RECIPIENT_TYPE_TO),
            ("Cc", RECIPIENT_TYPE_CC),
            ("Bcc", RECIPIENT_TYPE_BCC),
        ):
            header_values = [str(value) for value in email_message.get_all(header_name, [])]
            for display_name, address in getaddresses(header_values):
                if not address:
                    continue
                message.add_recipient(
                    address,
                    display_name=display_name or address,
                    recipient_type=recipient_type,
                )

        plain_body, html_body = _extract_email_bodies(email_message)
        if plain_body is not None:
            message.body = plain_body
        if html_body is not None:
            message.body_html = html_body

        transport_headers = _serialize_transport_headers(email_message, cls._TRANSPORT_HEADER_EXCLUDE)
        if transport_headers:
            message._set_string_property(int(CommonMessagePropertyId.TRANSPORT_MESSAGE_HEADERS), transport_headers)

        for part in email_message.iter_attachments():
            filename = part.get_filename() or "attachment.bin"
            content_id = part.get("Content-ID")
            mime_type = part.get_content_type()
            payload = part.get_content()
            if isinstance(payload, EmailMessage):
                attachment_message = cls.from_email_message(payload, unicode_strings=unicode_strings)
                attachment = message.add_embedded_message_attachment(
                    attachment_message,
                    filename=filename,
                    mime_type=mime_type,
                )
                attachment.content_id = content_id
                continue
            if part.get_content_maintype() == "message":
                raw_bytes = part.get_payload(decode=True)
                if raw_bytes:
                    nested = BytesParser(policy=policy.default).parsebytes(raw_bytes)
                    attachment_message = cls.from_email_message(nested, unicode_strings=unicode_strings)
                    attachment = message.add_embedded_message_attachment(
                        attachment_message,
                        filename=filename,
                        mime_type=mime_type,
                    )
                    attachment.content_id = content_id
                    continue
            if isinstance(payload, str):
                charset = part.get_content_charset() or "utf-8"
                data = payload.encode(charset, errors="replace")
            else:
                data = part.get_payload(decode=True)
                if data is None:
                    data = bytes(payload)
            message.add_attachment(filename, data, mime_type=mime_type, content_id=content_id)

        return message

    @classmethod
    def create(cls, subject: str = "", body: str = "", *, unicode_strings: bool = True) -> "MapiMessage":
        message = cls(unicode_strings=unicode_strings)
        if subject:
            message.subject = subject
        if body:
            message.body = body
        return message

    @property
    def msg_reader(self) -> MsgReader:
        if self._closed:
            raise RuntimeError("Message is closed.")
        if self._msg_reader is None:
            raise RuntimeError("Message is not initialized from .msg file.")
        return self._msg_reader

    @property
    def validation_issues(self) -> tuple[str, ...]:
        if self._msg_reader is not None:
            return self._msg_reader.validation_issues
        return self._validation_issues

    @property
    def subject(self) -> str | None:
        return _string_property_value(self.properties, int(CommonMessagePropertyId.SUBJECT))

    @subject.setter
    def subject(self, value: str) -> None:
        self._set_string_property(int(CommonMessagePropertyId.SUBJECT), value)

    @property
    def body(self) -> str | None:
        return _string_property_value(self.properties, int(CommonMessagePropertyId.BODY))

    @body.setter
    def body(self, value: str) -> None:
        self._set_string_property(int(CommonMessagePropertyId.BODY), value)

    @property
    def message_class(self) -> str | None:
        return _string_property_value(self.properties, int(CommonMessagePropertyId.MESSAGE_CLASS))

    @message_class.setter
    def message_class(self, value: str) -> None:
        self._set_string_property(int(CommonMessagePropertyId.MESSAGE_CLASS), value)

    @property
    def body_html(self) -> str | None:
        prop = self.properties.get(int(CommonMessagePropertyId.BODY_HTML), int(PropertyTypeCode.PTYP_STRING))
        if prop is not None and isinstance(prop.value, str):
            return prop.value
        raw = self.properties.get(int(CommonMessagePropertyId.BODY_HTML), int(PropertyTypeCode.PTYP_BINARY))
        if raw is not None and isinstance(raw.value, bytes):
            return raw.value.decode("utf-8", errors="replace").rstrip("\x00")
        return None

    @body_html.setter
    def body_html(self, value: str) -> None:
        self.set_property(int(CommonMessagePropertyId.BODY_HTML), PropertyTypeCode.PTYP_BINARY, value.encode("utf-8"))

    def iter_properties(self) -> Iterator[MapiProperty]:
        yield from self.properties.iter_properties()

    def iter_property_keys(self, storage_stream_id: int = 0) -> Iterator[tuple[int, int]]:
        properties, _, _ = self._resolve_storage_property_context(storage_stream_id)
        for prop in properties.iter_properties():
            yield (prop.property_id, prop.property_type)

    def set_property(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type_or_value: int | PropertyTypeCode | Any,
        value: Any = _MISSING,
        *,
        flags: int = DEFAULT_PROPERTY_FLAGS,
    ) -> MapiProperty:
        property_type, resolved_value = _resolve_set_property_args(property_id, property_type_or_value, value)
        property_id = int(property_id)
        prop = self.properties.add(property_id, property_type, resolved_value, flags=flags)
        if property_id == int(CommonMessagePropertyId.STORE_SUPPORT_MASK):
            self.unicode_strings = (int(resolved_value) & STORE_UNICODE_OK) != 0
            self.emit_store_support_mask = True
        return prop

    def get_property(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type: int | None = None,
        *,
        storage_stream_id: int | None = None,
        decode: bool | None = None,
    ) -> MapiProperty | Any | None:
        if storage_stream_id is not None or decode is not None:
            return self.get_property_value(
                property_id,
                property_type,
                storage_stream_id=storage_stream_id or 0,
                decode=True if decode is None else decode,
            )
        return self.properties.get(property_id, property_type)

    def get_property_value(
        self,
        property_id: int | CommonMessagePropertyId | PropertyId,
        property_type: int | None = None,
        *,
        storage_stream_id: int = 0,
        decode: bool = True,
    ) -> Any | None:
        property_key = property_id
        property_id = int(property_id)
        properties, role, attachment_method = self._resolve_storage_property_context(storage_stream_id)
        if property_type is not None:
            candidate_types = [int(property_type)]
        elif isinstance(property_key, PropertyId):
            candidate_types = [property_key.property_type]
            candidate_types.extend(
                int(value)
                for value in self._PREFERRED_PROPERTY_TYPES
                if int(value) != property_key.property_type
            )
        else:
            candidate_types = [int(value) for value in self._PREFERRED_PROPERTY_TYPES]
        for candidate_type in candidate_types:
            prop = properties.get(int(property_id), candidate_type)
            if prop is None:
                continue
            if decode:
                return prop.value
            return _raw_property_value(
                prop,
                role=role,
                attachment_method=attachment_method,
            )
        return None

    def set_named_property(
        self,
        named_property: MapiNamedProperty,
        property_type: int | PropertyTypeCode,
        value: Any,
        *,
        flags: int = DEFAULT_PROPERTY_FLAGS,
    ) -> MapiProperty:
        resolved = self.nameid_mapping.ensure(named_property, preferred_property_id=named_property.property_id)
        return self.properties.add(resolved.property_id or 0, property_type, value, flags=flags, named=resolved)

    def get_named_property(
        self, named_property: MapiNamedProperty, property_type: int | None = None
    ) -> MapiProperty | None:
        resolved = self.nameid_mapping.ensure(named_property, preferred_property_id=named_property.property_id)
        return self.properties.get(resolved.property_id or 0, property_type)

    def add_recipient(
        self,
        email_address: str,
        *,
        display_name: str | None = None,
        recipient_type: int = RECIPIENT_TYPE_TO,
    ) -> MapiRecipient:
        recipient = MapiRecipient(display_name=display_name or email_address, email_address=email_address, recipient_type=recipient_type)
        self.recipients.append(recipient)
        self.preserve_declared_header_counts = False
        return recipient

    def add_attachment(
        self,
        filename: str,
        data: bytes,
        *,
        mime_type: str | None = None,
        content_id: str | None = None,
    ) -> MapiAttachment:
        attachment = MapiAttachment.from_bytes(filename, data, mime_type=mime_type, content_id=content_id)
        self.attachments.append(attachment)
        self.preserve_declared_header_counts = False
        return attachment

    def add_embedded_message_attachment(
        self, message: "MapiMessage", *, filename: str | None = None, mime_type: str | None = None
    ) -> MapiAttachment:
        attachment = MapiAttachment.from_embedded_message(message, filename=filename, mime_type=mime_type)
        self.attachments.append(attachment)
        self.preserve_declared_header_counts = False
        return attachment

    def save(self, path: Path | str) -> None:
        MsgWriter.write_file(self.to_msg_document(), path)

    def to_bytes(self) -> bytes:
        return MsgWriter.to_bytes(self.to_msg_document())

    def to_email_message(self) -> EmailMessage:
        email_message = EmailMessage(policy=policy.default)

        transport_headers = _string_property_value(self.properties, int(CommonMessagePropertyId.TRANSPORT_MESSAGE_HEADERS))
        if transport_headers:
            parsed = Parser(policy=policy.default).parsestr(transport_headers)
            for key, value in parsed.items():
                if key.lower() in self._SKIP_IMPORTED_HEADERS:
                    continue
                safe_value = str(value).replace("\r", " ").replace("\n", " ")
                if key not in email_message:
                    try:
                        email_message[key] = safe_value
                    except (TypeError, ValueError):
                        continue

        self._set_email_header_if_missing(email_message, "Subject", self.subject)
        self._set_email_header_if_missing(email_message, "To", _format_recipient_header(self.recipients, RECIPIENT_TYPE_TO))
        self._set_email_header_if_missing(email_message, "Cc", _format_recipient_header(self.recipients, RECIPIENT_TYPE_CC))
        self._set_email_header_if_missing(email_message, "Bcc", _format_recipient_header(self.recipients, RECIPIENT_TYPE_BCC))
        self._set_email_header_if_missing(
            email_message,
            "Message-ID",
            _string_property_value(self.properties, int(CommonMessagePropertyId.INTERNET_MESSAGE_ID)),
        )

        sender_name = _string_property_value(self.properties, int(CommonMessagePropertyId.SENDER_NAME))
        sender_address = _string_property_value(self.properties, int(CommonMessagePropertyId.SENDER_EMAIL_ADDRESS))
        if sender_address:
            try:
                self._set_email_header_if_missing(email_message, "From", formataddr((sender_name or "", sender_address)))
            except (TypeError, UnicodeEncodeError, ValueError):
                self._set_email_header_if_missing(email_message, "From", sender_name or sender_address)

        delivered = self.properties.get(int(CommonMessagePropertyId.MESSAGE_DELIVERY_TIME), int(PropertyTypeCode.PTYP_TIME))
        if delivered is not None and isinstance(delivered.value, datetime):
            self._set_email_header_if_missing(email_message, "Date", format_datetime(delivered.value))

        plain_body = self.body
        html_body = self.body_html
        if plain_body:
            email_message.set_content(plain_body)
            if html_body:
                email_message.add_alternative(html_body, subtype="html")
        elif html_body:
            email_message.set_content(html_body, subtype="html")
        else:
            email_message.set_content("")

        for attachment in self.attachments:
            mime_type = attachment.mime_type or mimetypes.guess_type(attachment.filename or "")[0]
            if attachment.is_embedded_message:
                mime_type = mime_type or "message/rfc822"
                email_message.add_attachment(
                    attachment.embedded_message.to_email_bytes() if attachment.embedded_message is not None else attachment.data,
                    maintype="message",
                    subtype="rfc822",
                    filename=attachment.filename or "message.msg",
                )
            else:
                maintype, subtype = self._split_mime(mime_type or "application/octet-stream")
                email_message.add_attachment(
                    attachment.data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment.filename,
                )
            if attachment.content_id:
                email_message.get_payload()[-1]["Content-ID"] = attachment.content_id

        return email_message

    def to_email_bytes(self, *args, **kwargs) -> bytes:
        return self.to_email_message().as_bytes(*args, **kwargs)

    def to_email_string(self, *args, **kwargs) -> str:
        return self.to_email_message().as_string(*args, **kwargs)

    def iter_attachments_info(self) -> Iterator[MapiAttachment]:
        for attachment in self.attachments:
            yield attachment

    def close(self) -> None:
        if self._closed:
            return
        if self._msg_reader is not None:
            self._msg_reader.close()
        self._closed = True

    def __enter__(self) -> "MapiMessage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def to_msg_document(self) -> MsgDocument:
        self._normalize_top_level_properties()
        recipient_count = len(self.recipients)
        attachment_count = len(self.attachments)
        next_recipient_id = _next_storage_id(self.recipients)
        next_attachment_id = _next_storage_id(self.attachments)
        if self.preserve_declared_header_counts:
            if self.declared_recipient_count is not None:
                recipient_count = self.declared_recipient_count
            if self.declared_attachment_count is not None:
                attachment_count = self.declared_attachment_count
            if self.declared_next_recipient_id is not None:
                next_recipient_id = self.declared_next_recipient_id
            if self.declared_next_attachment_id is not None:
                next_attachment_id = self.declared_next_attachment_id
        root = MsgStorage(name="Root Entry", role=MESSAGE_ROLE)
        root.storages.append(self.nameid_mapping.to_storage())
        root.streams.extend(_clone_msg_stream(stream) for stream in self.extra_streams)
        root.storages.extend(_clone_msg_storage(storage) for storage in self.extra_storages)

        property_stream, value_streams = _serialize_property_bag(
            self.properties,
            role=MESSAGE_ROLE,
            header_reserved_0=self.header_reserved_0,
            header_reserved_1=self.header_reserved_1,
            attachment_method=None,
            recipient_count=recipient_count,
            attachment_count=attachment_count,
            next_recipient_id=next_recipient_id,
            next_attachment_id=next_attachment_id,
        )
        root.streams.append(property_stream)
        root.streams.extend(value_streams)

        for index, recipient in enumerate(self.recipients):
            root.storages.append(_recipient_to_storage(recipient, index, self.unicode_strings))
        for index, attachment in enumerate(self.attachments):
            root.storages.append(_attachment_to_storage(attachment, index, self.unicode_strings))

        return MsgDocument(
            root=root,
            major_version=self.major_version,
            minor_version=self.minor_version,
            transaction_signature_number=self.transaction_signature_number,
        )

    def _normalize_top_level_properties(self) -> None:
        if self.emit_store_support_mask:
            existing = self.properties.get(int(CommonMessagePropertyId.STORE_SUPPORT_MASK), int(PropertyTypeCode.PTYP_INTEGER32))
            if existing is None:
                store_support_mask = STORE_UNICODE_OK if self.unicode_strings else 0
                self.set_property(int(CommonMessagePropertyId.STORE_SUPPORT_MASK), PropertyTypeCode.PTYP_INTEGER32, store_support_mask)
        if not self.emit_compatibility_defaults:
            return
        if self.properties.get(int(CommonMessagePropertyId.MESSAGE_CLASS)) is None:
            self._set_string_property(int(CommonMessagePropertyId.MESSAGE_CLASS), DEFAULT_MESSAGE_CLASS)
        if (
            self.properties.get(int(CommonMessagePropertyId.SENDER_ADDRESS_TYPE)) is None
            and self.properties.get(int(CommonMessagePropertyId.SENDER_EMAIL_ADDRESS)) is not None
        ):
            self._set_string_property(int(CommonMessagePropertyId.SENDER_ADDRESS_TYPE), DEFAULT_SMTP_ADDRESS_TYPE)
        self._ensure_sender_compatibility_properties()
        self._ensure_message_compatibility_properties()
        self._ensure_display_recipient_properties()

    def _set_string_property(self, property_id: int, value: str) -> None:
        property_type = PropertyTypeCode.PTYP_STRING if self.unicode_strings else PropertyTypeCode.PTYP_STRING8
        self.set_property(property_id, property_type, value)

    def _ensure_display_recipient_properties(self) -> None:
        for property_id, recipient_type in (
            (int(CommonMessagePropertyId.DISPLAY_TO), RECIPIENT_TYPE_TO),
            (int(CommonMessagePropertyId.DISPLAY_CC), RECIPIENT_TYPE_CC),
            (int(CommonMessagePropertyId.DISPLAY_BCC), RECIPIENT_TYPE_BCC),
        ):
            if self.properties.get(property_id) is not None:
                continue
            display_value = _format_recipient_header(self.recipients, recipient_type)
            if display_value:
                self._set_string_property(property_id, display_value)

    def _ensure_sender_compatibility_properties(self) -> None:
        sender_email = _string_property_value(self.properties, int(CommonMessagePropertyId.SENDER_EMAIL_ADDRESS))
        if not sender_email:
            return
        sender_name = _string_property_value(self.properties, int(CommonMessagePropertyId.SENDER_NAME)) or sender_email
        sender_address_type = (
            _string_property_value(self.properties, int(CommonMessagePropertyId.SENDER_ADDRESS_TYPE))
            or DEFAULT_SMTP_ADDRESS_TYPE
        )
        search_key = _smtp_search_key(sender_email)
        entry_id = _build_one_off_entry_id(
            display_name=sender_name,
            address_type=sender_address_type,
            email_address=sender_email,
            unicode_strings=self.unicode_strings,
        )
        self._set_missing_binary_property(SENDER_SEARCH_KEY_PROPERTY_ID, search_key)
        self._set_missing_binary_property(SENDER_ENTRY_ID_PROPERTY_ID, entry_id)
        self._set_missing_binary_property(SENT_REPRESENTING_SEARCH_KEY_PROPERTY_ID, search_key)
        self._set_missing_binary_property(SENT_REPRESENTING_ENTRY_ID_PROPERTY_ID, entry_id)
        self._set_missing_string_property(SENT_REPRESENTING_NAME_PROPERTY_ID, sender_name)
        self._set_missing_string_property(SENT_REPRESENTING_ADDRESS_TYPE_PROPERTY_ID, sender_address_type)
        self._set_missing_string_property(SENT_REPRESENTING_EMAIL_ADDRESS_PROPERTY_ID, sender_email)

    def _ensure_message_compatibility_properties(self) -> None:
        subject = self.subject
        self._set_missing_property(IMPORTANCE_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, DEFAULT_IMPORTANCE)
        self._set_missing_property(SENSITIVITY_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, DEFAULT_SENSITIVITY)
        if subject:
            self._set_missing_string_property(CONVERSATION_TOPIC_PROPERTY_ID, subject)
            self._set_missing_string_property(NORMALIZED_SUBJECT_PROPERTY_ID, subject)
        if self.properties.get(CONVERSATION_INDEX_PROPERTY_ID, int(PropertyTypeCode.PTYP_BINARY)) is None:
            self.set_property(
                CONVERSATION_INDEX_PROPERTY_ID,
                PropertyTypeCode.PTYP_BINARY,
                _build_conversation_index(self),
            )
        self._set_missing_property(
            CONVERSATION_INDEX_TRACKING_PROPERTY_ID,
            PropertyTypeCode.PTYP_BOOLEAN,
            True,
        )
        if self.properties.get(SEARCH_KEY_PROPERTY_ID, int(PropertyTypeCode.PTYP_BINARY)) is None:
            self.set_property(
                SEARCH_KEY_PROPERTY_ID,
                PropertyTypeCode.PTYP_BINARY,
                _stable_binary_key("message-search-key", self.subject or "", self.message_class or ""),
            )
        delivered = self.properties.get(int(CommonMessagePropertyId.MESSAGE_DELIVERY_TIME), int(PropertyTypeCode.PTYP_TIME))
        if delivered is not None and isinstance(delivered.value, datetime):
            self._set_missing_property(CLIENT_SUBMIT_TIME_PROPERTY_ID, PropertyTypeCode.PTYP_TIME, delivered.value)
        message_flags = MESSAGE_FLAG_READ
        if self.attachments:
            message_flags |= MESSAGE_FLAG_HASATTACH
        self._set_missing_property(
            int(CommonMessagePropertyId.MESSAGE_FLAGS),
            PropertyTypeCode.PTYP_INTEGER32,
            message_flags,
        )
        self._set_missing_property(
            int(CommonMessagePropertyId.INTERNET_CODEPAGE),
            PropertyTypeCode.PTYP_INTEGER32,
            _default_internet_codepage(self),
        )

    def _set_missing_property(
        self,
        property_id: int,
        property_type: int | PropertyTypeCode,
        value: Any,
    ) -> None:
        if self.properties.get(property_id, int(property_type)) is None:
            self.set_property(property_id, property_type, value)

    def _set_missing_string_property(self, property_id: int, value: str) -> None:
        if self.properties.get(property_id) is None:
            self._set_string_property(property_id, value)

    def _set_missing_binary_property(self, property_id: int, value: bytes) -> None:
        if self.properties.get(property_id, int(PropertyTypeCode.PTYP_BINARY)) is None:
            self.set_property(property_id, PropertyTypeCode.PTYP_BINARY, value)

    @staticmethod
    def _set_email_header_if_missing(email_message: EmailMessage, key: str, value: str | None) -> None:
        if not value or key in email_message:
            return
        try:
            email_message[key] = value
        except (TypeError, ValueError):
            return

    @classmethod
    def _split_mime(cls, mime_value: str) -> tuple[str, str]:
        if "/" in mime_value:
            maintype, subtype = mime_value.split("/", 1)
            maintype = maintype.strip().lower()
            subtype = subtype.strip().lower()
            if maintype and subtype and maintype in cls._KNOWN_MIME_MAINTYPES and maintype not in {"multipart", "message"}:
                return maintype, subtype
        return ("application", "octet-stream")

    @staticmethod
    def _encoding_from_codepage(codepage: int) -> str | None:
        if codepage <= 0:
            return None
        if codepage == 65001:
            return "utf-8"
        if codepage == 1200:
            return "utf-16-le"
        if codepage == 1201:
            return "utf-16-be"
        return f"cp{codepage}"

    def _resolve_storage_property_context(
        self,
        storage_stream_id: int,
    ) -> tuple[MapiPropertyCollection, str, int | None]:
        if storage_stream_id == 0:
            return (self.properties, MESSAGE_ROLE, None)
        for recipient in self.recipients:
            if recipient.storage_id == storage_stream_id:
                return (recipient.properties, RECIPIENT_ROLE, None)
        for attachment in self.attachments:
            if attachment.storage_id == storage_stream_id:
                return (attachment.properties, ATTACHMENT_ROLE, attachment.attach_method)
        raise MsgError(f"Unknown storage_stream_id for MapiMessage property lookup: {storage_stream_id}")


def _coerce_uuid(value: uuid.UUID | str | bytes) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, bytes):
        if len(value) != 16:
            raise ValueError("UUID byte value must be exactly 16 bytes long.")
        return uuid.UUID(bytes_le=value)
    return uuid.UUID(str(value))


def _guid_from_index(guid_index: int, guid_list: list[uuid.UUID]) -> uuid.UUID:
    if guid_index == 1:
        return PS_MAPI
    if guid_index == 2:
        return PS_PUBLIC_STRINGS
    return guid_list[guid_index - 3]


def _named_property_key(identity: MapiNamedProperty) -> tuple[uuid.UUID, str, str | int]:
    return (
        _coerce_uuid(identity.property_set),
        identity.kind,
        identity.name if identity.kind == "string" else int(identity.lid or 0),
    )


def _parse_nameid_string_stream(data: bytes) -> dict[int, str]:
    names: dict[int, str] = {}
    offset = 0
    while offset + 4 <= len(data):
        name_length = struct.unpack_from("<I", data, offset)[0]
        start = offset + 4
        end = start + name_length
        if end > len(data):
            break
        names[offset] = data[start:end].decode("utf-16-le")
        offset = end
        while offset % 4:
            offset += 1
    return names


def _string_property_value(properties: MapiPropertyCollection, property_id: int) -> str | None:
    for property_type in (int(PropertyTypeCode.PTYP_STRING), int(PropertyTypeCode.PTYP_STRING8)):
        prop = properties.get(property_id, property_type)
        if prop is not None and isinstance(prop.value, str):
            return prop.value
    return None


def _resolve_property_type(
    property_id: int | CommonMessagePropertyId | PropertyId,
    property_type: int | None,
) -> int | None:
    if property_type is not None:
        return int(property_type)
    if isinstance(property_id, PropertyId):
        return property_id.property_type
    return None


def _resolve_set_property_args(
    property_id: int | CommonMessagePropertyId | PropertyId,
    property_type_or_value: int | PropertyTypeCode | Any,
    value: Any,
) -> tuple[int, Any]:
    if value is _MISSING:
        if not isinstance(property_id, PropertyId):
            raise TypeError("property_type is required unless property_id is a typed PropertyId member.")
        return (property_id.property_type, property_type_or_value)
    return (int(property_type_or_value), value)


def _format_recipient_header(recipients: Iterable[MapiRecipient], recipient_type: int) -> str | None:
    values: list[str] = []
    for recipient in recipients:
        if recipient.recipient_type != recipient_type or not recipient.email_address:
            continue
        try:
            values.append(formataddr((recipient.display_name or "", recipient.email_address)))
        except (TypeError, UnicodeEncodeError, ValueError):
            values.append(recipient.display_name or recipient.email_address)
    if not values:
        return None
    return ", ".join(values)


def _smtp_search_key(email_address: str) -> bytes:
    normalized = email_address.strip().upper()
    return f"SMTP:{normalized}".encode("ascii", errors="ignore") + b"\x00"


def _stable_binary_key(kind: str, *parts: str, size: int = 16) -> bytes:
    seed = "\x1f".join((kind, *parts)).encode("utf-8", errors="replace")
    raw = uuid.uuid5(uuid.NAMESPACE_URL, seed.decode("utf-8", errors="replace")).bytes
    if size <= len(raw):
        return raw[:size]
    repeats = (size + len(raw) - 1) // len(raw)
    return (raw * repeats)[:size]


def _stable_u32(key: str, *parts: str) -> int:
    seed = "\x1f".join((key, *parts)).encode("utf-8", errors="replace")
    return binascii.crc32(seed) & 0xFFFFFFFF


def _build_conversation_index(message: MapiMessage) -> bytes:
    delivered = message.properties.get(int(CommonMessagePropertyId.MESSAGE_DELIVERY_TIME), int(PropertyTypeCode.PTYP_TIME))
    timestamp = delivered.value if delivered is not None and isinstance(delivered.value, datetime) else datetime.now(UTC)
    filetime = _datetime_to_filetime(timestamp)
    time_prefix = filetime.to_bytes(8, "big", signed=False)[:5]
    sender = _string_property_value(message.properties, int(CommonMessagePropertyId.SENDER_EMAIL_ADDRESS)) or ""
    internet_id = _string_property_value(message.properties, int(CommonMessagePropertyId.INTERNET_MESSAGE_ID)) or ""
    guid = uuid.uuid5(uuid.NAMESPACE_URL, "\x1f".join((message.subject or "", sender, internet_id)))
    return b"\x01" + time_prefix + guid.bytes


def _default_internet_codepage(message: MapiMessage) -> int:
    if message.body_html:
        return DEFAULT_INTERNET_CODEPAGE
    return DEFAULT_INTERNET_CODEPAGE_ASCII


def _build_one_off_entry_id(
    *,
    display_name: str,
    address_type: str,
    email_address: str,
    unicode_strings: bool,
) -> bytes:
    provider_uid = bytes.fromhex("812B1FA4BEA310199D6E00DD010F5402")
    version = 0
    flags = 0x0001 | (0x8000 if unicode_strings else 0)
    payload = bytearray()
    payload.extend(struct.pack("<I", 0))
    payload.extend(provider_uid)
    payload.extend(struct.pack("<HH", version, flags))
    if unicode_strings:
        for value in (display_name, address_type, email_address):
            payload.extend(value.encode("utf-16-le"))
            payload.extend(b"\x00\x00")
    else:
        for value in (display_name, address_type, email_address):
            payload.extend(value.encode("ascii", errors="replace"))
            payload.extend(b"\x00")
    return bytes(payload)


def _serialize_transport_headers(email_message: EmailMessage, excluded: set[str]) -> str | None:
    lines: list[str] = []
    for key, value in email_message.raw_items():
        if key.lower() in excluded:
            continue
        lines.append(f"{key}: {value}")
    if not lines:
        return None
    return "\n".join(lines)


def _extract_email_bodies(email_message: EmailMessage) -> tuple[str | None, str | None]:
    plain_body: str | None = None
    html_body: str | None = None

    if email_message.is_multipart():
        plain_part = email_message.get_body(preferencelist=("plain",))
        html_part = email_message.get_body(preferencelist=("html",))
        if plain_part is not None:
            payload = plain_part.get_content()
            plain_body = payload if isinstance(payload, str) else bytes(payload).decode("utf-8", errors="replace")
        if html_part is not None:
            payload = html_part.get_content()
            html_body = payload if isinstance(payload, str) else bytes(payload).decode("utf-8", errors="replace")
        return (plain_body, html_body)

    payload = email_message.get_content()
    if email_message.get_content_type() == "text/html":
        html_body = payload if isinstance(payload, str) else bytes(payload).decode("utf-8", errors="replace")
    else:
        plain_body = payload if isinstance(payload, str) else bytes(payload).decode("utf-8", errors="replace")
    return (plain_body, html_body)


def _raw_property_value(
    property: MapiProperty,
    *,
    role: str,
    attachment_method: int | None,
) -> bytes | list[bytes]:
    if property.property_type in _FIXED_INLINE_SIZES:
        if property.raw_inline_value is not None:
            return property.raw_inline_value[: _FIXED_INLINE_SIZES[property.property_type]]
        return _encode_inline_value(property.property_type, property.value)[: _FIXED_INLINE_SIZES[property.property_type]]
    if property.raw_indexed_streams:
        return [bytes(payload) for _, payload in sorted(property.raw_indexed_streams)]
    if property.raw_direct_stream is not None:
        return bytes(property.raw_direct_stream)
    stream_payloads, _, _ = _encode_stream_property(
        property,
        role=role,
        attachment_method=attachment_method,
    )
    if len(stream_payloads) == 1:
        return stream_payloads[0][1]
    return [payload for _, payload in stream_payloads[1:]]


def _recipient_from_storage(storage: MsgStorage, mapping: _NamedPropertyMapping, unicode_strings: bool) -> MapiRecipient:
    properties, extra_streams, reserved_0, _ = _parse_property_storage(
        storage, mapping, role=RECIPIENT_ROLE, unicode_strings=unicode_strings
    )
    recipient = MapiRecipient(
        storage_id=_storage_id_from_name(storage.name),
        properties=properties,
        extra_streams=extra_streams,
        extra_storages=[_clone_msg_storage(child) for child in storage.storages],
        header_reserved_0=reserved_0,
    )
    recipient.display_name = _string_property_value(properties, DISPLAY_NAME_PROPERTY_ID)
    recipient.email_address = _string_property_value(properties, EMAIL_ADDRESS_PROPERTY_ID)
    recipient.address_type = _string_property_value(properties, ADDRESS_TYPE_PROPERTY_ID) or "SMTP"
    recipient_type_property = properties.get(RECIPIENT_TYPE_PROPERTY_ID, int(PropertyTypeCode.PTYP_INTEGER32))
    recipient.recipient_type = int(recipient_type_property.value) if recipient_type_property is not None else RECIPIENT_TYPE_TO
    return recipient


def _attachment_from_storage(storage: MsgStorage, mapping: _NamedPropertyMapping, unicode_strings: bool) -> MapiAttachment:
    properties, extra_streams, reserved_0, _ = _parse_property_storage(
        storage, mapping, role=ATTACHMENT_ROLE, unicode_strings=unicode_strings
    )
    attach_method_property = properties.get(int(CommonMessagePropertyId.ATTACH_METHOD), int(PropertyTypeCode.PTYP_INTEGER32))
    attach_method = int(attach_method_property.value) if attach_method_property is not None else ATTACH_METHOD_BY_VALUE
    filename = (
        _string_property_value(properties, int(CommonMessagePropertyId.ATTACH_LONG_FILENAME))
        or _string_property_value(properties, int(CommonMessagePropertyId.ATTACH_FILENAME))
    )
    mime_type = _string_property_value(properties, int(CommonMessagePropertyId.ATTACH_MIME_TAG))
    content_id = _string_property_value(properties, int(CommonMessagePropertyId.ATTACH_CONTENT_ID))
    data_property = properties.get(int(CommonMessagePropertyId.ATTACH_DATA_BINARY), int(PropertyTypeCode.PTYP_BINARY))
    attachment = MapiAttachment(
        filename=filename,
        data=data_property.value if data_property is not None and isinstance(data_property.value, bytes) else b"",
        mime_type=mime_type,
        content_id=content_id,
        attach_method=attach_method,
        storage_id=_storage_id_from_name(storage.name),
        properties=properties,
        extra_streams=extra_streams,
        header_reserved_0=reserved_0,
    )
    for child in storage.storages:
        if child.name != EMBEDDED_MESSAGE_STORAGE_NAME:
            continue
        if child.role == EMBEDDED_MESSAGE_ROLE:
            try:
                attachment.embedded_message = MapiMessage.from_msg_document(MsgDocument(root=_clone_msg_storage(child)))
            except MsgError:
                attachment.custom_storage = _clone_msg_storage(child)
        elif child.role == CUSTOM_ATTACHMENT_ROLE:
            attachment.custom_storage = _clone_msg_storage(child)
    return attachment


def _recipient_to_storage(recipient: MapiRecipient, index: int, unicode_strings: bool) -> MsgStorage:
    storage_id = recipient.storage_id if recipient.storage_id is not None else index
    _sync_property_value(recipient.properties, RECIPIENT_TYPE_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, recipient.recipient_type)
    if recipient.storage_id is None:
        _sync_property_value(recipient.properties, ROWID_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, index)
    if recipient.display_name and recipient.storage_id is None:
        _set_object_string_property(recipient.properties, DISPLAY_NAME_PROPERTY_ID, recipient.display_name, unicode_strings)
    if recipient.address_type and recipient.storage_id is None:
        _set_object_string_property(recipient.properties, ADDRESS_TYPE_PROPERTY_ID, recipient.address_type, unicode_strings)
    if recipient.email_address and recipient.storage_id is None:
        _set_object_string_property(recipient.properties, EMAIL_ADDRESS_PROPERTY_ID, recipient.email_address, unicode_strings)
        if recipient.storage_id is None and recipient.properties.get(SMTP_ADDRESS_PROPERTY_ID) is None:
            _set_object_string_property(recipient.properties, SMTP_ADDRESS_PROPERTY_ID, recipient.email_address, unicode_strings)
        if recipient.properties.get(SEARCH_KEY_PROPERTY_ID, int(PropertyTypeCode.PTYP_BINARY)) is None:
            recipient.properties.add(
                SEARCH_KEY_PROPERTY_ID,
                PropertyTypeCode.PTYP_BINARY,
                _smtp_search_key(recipient.email_address),
                flags=DEFAULT_PROPERTY_FLAGS,
            )
        if recipient.properties.get(RECIPIENT_ENTRY_ID_PROPERTY_ID, int(PropertyTypeCode.PTYP_BINARY)) is None:
            recipient.properties.add(
                RECIPIENT_ENTRY_ID_PROPERTY_ID,
                PropertyTypeCode.PTYP_BINARY,
                _build_one_off_entry_id(
                    display_name=recipient.display_name or recipient.email_address,
                    address_type=recipient.address_type or DEFAULT_SMTP_ADDRESS_TYPE,
                    email_address=recipient.email_address,
                    unicode_strings=unicode_strings,
                ),
                flags=DEFAULT_PROPERTY_FLAGS,
            )
        if recipient.properties.get(INSTANCE_KEY_PROPERTY_ID, int(PropertyTypeCode.PTYP_BINARY)) is None:
            recipient.properties.add(
                INSTANCE_KEY_PROPERTY_ID,
                PropertyTypeCode.PTYP_BINARY,
                struct.pack(
                    "<I",
                    _stable_u32(
                        "recipient-instance-key",
                        recipient.email_address,
                        str(recipient.recipient_type),
                        str(index),
                    ),
                ),
                flags=DEFAULT_PROPERTY_FLAGS,
            )
    recipient_storage = MsgStorage(name=f"{RECIPIENT_STORAGE_PREFIX}{storage_id:08X}", role=RECIPIENT_ROLE)
    property_stream, value_streams = _serialize_property_bag(
        recipient.properties,
        role=RECIPIENT_ROLE,
        header_reserved_0=recipient.header_reserved_0,
        header_reserved_1=b"",
        attachment_method=None,
    )
    recipient_storage.streams.append(property_stream)
    recipient_storage.streams.extend(value_streams)
    recipient_storage.streams.extend(_clone_msg_stream(stream) for stream in recipient.extra_streams)
    recipient_storage.storages.extend(_clone_msg_storage(storage) for storage in recipient.extra_storages)
    return recipient_storage


def _attachment_to_storage(attachment: MapiAttachment, index: int, unicode_strings: bool) -> MsgStorage:
    storage_id = attachment.storage_id if attachment.storage_id is not None else index
    attachment_storage = MsgStorage(name=f"{ATTACHMENT_STORAGE_PREFIX}{storage_id:08X}", role=ATTACHMENT_ROLE)

    if attachment.storage_id is None:
        _sync_property_value(attachment.properties, ACCESS_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, DEFAULT_ACCESS)
        _sync_property_value(attachment.properties, ACCESS_LEVEL_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, DEFAULT_ACCESS_LEVEL)
        if attachment.properties.get(RECORD_KEY_PROPERTY_ID, int(PropertyTypeCode.PTYP_BINARY)) is None:
            attachment.properties.add(
                RECORD_KEY_PROPERTY_ID,
                PropertyTypeCode.PTYP_BINARY,
                struct.pack("<I", storage_id),
                flags=DEFAULT_PROPERTY_FLAGS,
            )
        if attachment.attach_method == ATTACH_METHOD_EMBEDDED:
            _sync_property_value(
                attachment.properties,
                int(CommonMessagePropertyId.ATTACH_METHOD),
                PropertyTypeCode.PTYP_INTEGER32,
                ATTACH_METHOD_EMBEDDED,
            )
            _sync_property_value(
                attachment.properties,
                int(CommonMessagePropertyId.ATTACH_DATA_BINARY),
                PropertyTypeCode.PTYP_OBJECT,
                None,
            )
        elif attachment.attach_method == ATTACH_METHOD_STORAGE:
            _sync_property_value(
                attachment.properties,
                int(CommonMessagePropertyId.ATTACH_METHOD),
                PropertyTypeCode.PTYP_INTEGER32,
                ATTACH_METHOD_STORAGE,
            )
            _sync_property_value(
                attachment.properties,
                int(CommonMessagePropertyId.ATTACH_DATA_BINARY),
                PropertyTypeCode.PTYP_OBJECT,
                None,
            )
        else:
            _sync_property_value(
                attachment.properties,
                int(CommonMessagePropertyId.ATTACH_METHOD),
                PropertyTypeCode.PTYP_INTEGER32,
                ATTACH_METHOD_BY_VALUE,
            )
            _sync_property_value(
                attachment.properties,
                int(CommonMessagePropertyId.ATTACH_DATA_BINARY),
                PropertyTypeCode.PTYP_BINARY,
                bytes(attachment.data),
            )
            if attachment.properties.get(0x370A, int(PropertyTypeCode.PTYP_BINARY)) is None:
                attachment.properties.add(
                    0x370A,
                    PropertyTypeCode.PTYP_BINARY,
                    DEFAULT_ATTACH_TAG,
                    flags=DEFAULT_PROPERTY_FLAGS,
                )

    if attachment.filename and attachment.storage_id is None:
        if attachment.properties.get(int(CommonMessagePropertyId.ATTACH_FILENAME)) is not None or attachment.storage_id is None:
            _set_object_string_property(
                attachment.properties, int(CommonMessagePropertyId.ATTACH_FILENAME), _short_filename(attachment.filename), unicode_strings
            )
        if attachment.properties.get(int(CommonMessagePropertyId.ATTACH_LONG_FILENAME)) is not None or attachment.storage_id is None:
            _set_object_string_property(
                attachment.properties, int(CommonMessagePropertyId.ATTACH_LONG_FILENAME), attachment.filename, unicode_strings
            )
        if attachment.properties.get(ATTACH_LONG_PATHNAME_PROPERTY_ID) is not None or attachment.storage_id is None:
            _set_object_string_property(
                attachment.properties, ATTACH_LONG_PATHNAME_PROPERTY_ID, attachment.filename, unicode_strings
            )
        extension = Path(attachment.filename).suffix
        if extension and (attachment.properties.get(ATTACH_EXTENSION_PROPERTY_ID) is not None or attachment.storage_id is None):
            _set_object_string_property(attachment.properties, ATTACH_EXTENSION_PROPERTY_ID, extension, unicode_strings)
    if attachment.mime_type and attachment.storage_id is None:
        if attachment.properties.get(int(CommonMessagePropertyId.ATTACH_MIME_TAG)) is not None or attachment.storage_id is None:
            _set_object_string_property(
                attachment.properties, int(CommonMessagePropertyId.ATTACH_MIME_TAG), attachment.mime_type, unicode_strings
            )
    elif attachment.filename and attachment.storage_id is None:
        guessed_mime = mimetypes.guess_type(attachment.filename)[0]
        if guessed_mime:
            _set_object_string_property(attachment.properties, int(CommonMessagePropertyId.ATTACH_MIME_TAG), guessed_mime, unicode_strings)
    if attachment.content_id and attachment.storage_id is None:
        if attachment.properties.get(int(CommonMessagePropertyId.ATTACH_CONTENT_ID)) is not None or attachment.storage_id is None:
            _set_object_string_property(
                attachment.properties, int(CommonMessagePropertyId.ATTACH_CONTENT_ID), attachment.content_id, unicode_strings
            )
    if attachment.storage_id is None:
        _sync_property_value(attachment.properties, ATTACH_NUM_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, storage_id)
    if attachment.storage_id is None:
        _sync_property_value(attachment.properties, ATTACH_SIZE_PROPERTY_ID, PropertyTypeCode.PTYP_INTEGER32, len(attachment.data))

    property_stream, value_streams = _serialize_property_bag(
        attachment.properties,
        role=ATTACHMENT_ROLE,
        header_reserved_0=attachment.header_reserved_0,
        header_reserved_1=b"",
        attachment_method=attachment.attach_method,
    )
    attachment_storage.streams.append(property_stream)
    attachment_storage.streams.extend(value_streams)
    attachment_storage.streams.extend(_clone_msg_stream(stream) for stream in attachment.extra_streams)

    if attachment.embedded_message is not None:
        embedded_document = attachment.embedded_message.to_msg_document()
        embedded_root = embedded_document.root
        embedded_root.name = EMBEDDED_MESSAGE_STORAGE_NAME
        embedded_root.role = EMBEDDED_MESSAGE_ROLE
        embedded_root.storages = [storage for storage in embedded_root.storages if storage.name != NAMED_PROPERTY_MAPPING_STORAGE_NAME]
        attachment_storage.storages.append(embedded_root)
    elif attachment.custom_storage is not None:
        custom_storage = _clone_msg_storage(attachment.custom_storage)
        custom_storage.name = EMBEDDED_MESSAGE_STORAGE_NAME
        custom_storage.role = CUSTOM_ATTACHMENT_ROLE
        attachment_storage.storages.append(custom_storage)
    return attachment_storage


def _set_object_string_property(
    properties: MapiPropertyCollection, property_id: int, value: str, unicode_strings: bool
) -> None:
    property_type = PropertyTypeCode.PTYP_STRING if unicode_strings else PropertyTypeCode.PTYP_STRING8
    _sync_property_value(properties, property_id, property_type, value)


def _sync_property_value(
    properties: MapiPropertyCollection,
    property_id: int,
    property_type: int | PropertyTypeCode,
    value: Any,
    *,
    flags: int = DEFAULT_PROPERTY_FLAGS,
) -> MapiProperty:
    existing = properties.get(property_id, int(property_type))
    if existing is not None and existing.value == value:
        return existing
    return properties.add(property_id, property_type, value, flags=flags)


def _storage_id_from_name(name: str) -> int | None:
    if "#" not in name:
        return None
    try:
        return int(name.rsplit("#", 1)[1], 16)
    except ValueError:
        return None


def _next_storage_id(items: Iterable[Any]) -> int:
    values = [int(item.storage_id) for item in items if getattr(item, "storage_id", None) is not None]
    return (max(values) + 1) if values else len(list(items))


def _short_filename(value: str) -> str:
    name = Path(value).name
    if len(name) <= 12:
        return name
    stem = Path(name).stem[:8]
    suffix = Path(name).suffix[:4]
    return f"{stem}{suffix}"


def _parse_property_storage(
    storage: MsgStorage,
    mapping: _NamedPropertyMapping,
    *,
    role: str,
    unicode_strings: bool,
) -> tuple[MapiPropertyCollection, list[MsgStream], bytes, bytes]:
    properties = MapiPropertyCollection()
    property_stream = storage.find_stream(PROPERTY_STREAM_NAME)
    direct_streams: dict[tuple[int, int], bytes] = {}
    indexed_streams: dict[tuple[int, int], dict[int, bytes]] = {}
    extra_streams: list[MsgStream] = []
    used_stream_names = {PROPERTY_STREAM_NAME}

    for stream in storage.streams:
        if stream.name == PROPERTY_STREAM_NAME:
            continue
        indexed_match = _STREAM_PROP_INDEXED_RE.match(stream.name)
        if indexed_match:
            key = (int(indexed_match.group(1), 16), int(indexed_match.group(2), 16))
            indexed_streams.setdefault(key, {})[int(indexed_match.group(3), 16)] = stream.data
            continue
        direct_match = _STREAM_PROP_RE.match(stream.name)
        if direct_match:
            direct_streams[(int(direct_match.group(1), 16), int(direct_match.group(2), 16))] = stream.data
            continue
        extra_streams.append(_clone_msg_stream(stream))

    reserved_0 = b"\x00" * 8
    reserved_1 = b"\x00" * 8
    entries = []
    if property_stream is not None:
        if role in {MESSAGE_ROLE, EMBEDDED_MESSAGE_ROLE}:
            header, entries = MsgReader.parse_top_level_property_stream(property_stream.data)
            reserved_0 = header.reserved_0
            reserved_1 = header.reserved_1
        else:
            header, entries = MsgReader.parse_subobject_property_stream_data(property_stream.data)
            reserved_0 = header.reserved_0

    for entry in entries:
        property_id = entry.property_tag >> 16
        property_type = entry.property_tag & 0xFFFF
        named = mapping.get_by_property_id(property_id) if property_id >= 0x8000 else None
        value = _decode_property_entry_value(
            property_type,
            entry.value,
            direct_streams.get((property_id, property_type)),
            indexed_streams.get((property_id, property_type)),
            unicode_strings=unicode_strings,
        )
        properties.set(
            MapiProperty(
                property_id=property_id,
                property_type=property_type,
                value=value,
                flags=entry.flags,
                named=named,
                raw_inline_value=entry.value if property_type in _FIXED_INLINE_SIZES else None,
                raw_size_value=None if property_type in _FIXED_INLINE_SIZES else struct.unpack_from("<I", entry.value, 0)[0],
                raw_reserved_value=None if property_type in _FIXED_INLINE_SIZES else struct.unpack_from("<I", entry.value, 4)[0],
                raw_direct_stream=bytes(direct_streams[(property_id, property_type)])
                if (property_id, property_type) in direct_streams
                else None,
                raw_indexed_streams=tuple(
                    (index, bytes(payload))
                    for index, payload in sorted(indexed_streams.get((property_id, property_type), {}).items())
                ),
                preserve_raw=True,
            )
        )
        if (property_id, property_type) in direct_streams:
            used_stream_names.add(_value_stream_name(property_id, property_type))
        for index in indexed_streams.get((property_id, property_type), {}):
            used_stream_names.add(_indexed_value_stream_name(property_id, property_type, index))

    for stream in storage.streams:
        if stream.name in used_stream_names or stream.name == PROPERTY_STREAM_NAME:
            continue
        if _STREAM_PROP_RE.match(stream.name) or _STREAM_PROP_INDEXED_RE.match(stream.name):
            extra_streams.append(_clone_msg_stream(stream))
    return properties, extra_streams, reserved_0, reserved_1


def _serialize_property_bag(
    properties: MapiPropertyCollection,
    *,
    role: str,
    header_reserved_0: bytes,
    header_reserved_1: bytes,
    attachment_method: int | None = None,
    recipient_count: int = 0,
    attachment_count: int = 0,
    next_recipient_id: int = 0,
    next_attachment_id: int = 0,
) -> tuple[MsgStream, list[MsgStream]]:
    property_stream = bytearray()
    if role in {MESSAGE_ROLE, EMBEDDED_MESSAGE_ROLE}:
        property_stream.extend(header_reserved_0.ljust(8, b"\x00")[:8])
        property_stream.extend(struct.pack("<I", next_recipient_id if recipient_count else 0))
        property_stream.extend(struct.pack("<I", next_attachment_id if attachment_count else 0))
        property_stream.extend(struct.pack("<I", recipient_count))
        property_stream.extend(struct.pack("<I", attachment_count))
        property_stream.extend(header_reserved_1.ljust(8, b"\x00")[:8])
    else:
        property_stream.extend(header_reserved_0.ljust(8, b"\x00")[:8])

    value_streams: list[MsgStream] = []
    for property in properties.iter_properties():
        property_tag = (property.property_id << 16) | property.property_type
        property_stream.extend(struct.pack("<I", property_tag))
        property_stream.extend(struct.pack("<I", property.flags))
        if property.preserve_raw and _property_has_complete_raw_payload(property):
            _append_preserved_property(property_stream, value_streams, property)
            continue
        if property.property_type in _FIXED_INLINE_SIZES:
            property_stream.extend(_encode_inline_value(property.property_type, property.value))
            continue

        stream_payloads, size_value, reserved_value = _encode_stream_property(
            property,
            role=role,
            attachment_method=attachment_method,
        )
        property_stream.extend(struct.pack("<I", size_value))
        property_stream.extend(struct.pack("<I", reserved_value))
        for stream_name, payload in stream_payloads:
            value_streams.append(MsgStream(stream_name, payload))

    return MsgStream(PROPERTY_STREAM_NAME, bytes(property_stream)), value_streams


def _property_has_complete_raw_payload(property: MapiProperty) -> bool:
    if property.property_type in _FIXED_INLINE_SIZES:
        return property.raw_inline_value is not None
    return property.raw_size_value is not None and property.raw_reserved_value is not None


def _append_preserved_property(
    property_stream: bytearray,
    value_streams: list[MsgStream],
    property: MapiProperty,
) -> None:
    if property.property_type in _FIXED_INLINE_SIZES:
        property_stream.extend((property.raw_inline_value or b"").ljust(8, b"\x00")[:8])
        if property.raw_direct_stream is not None:
            value_streams.append(MsgStream(_value_stream_name(property.property_id, property.property_type), bytes(property.raw_direct_stream)))
        return

    property_stream.extend(struct.pack("<I", int(property.raw_size_value or 0)))
    property_stream.extend(struct.pack("<I", int(property.raw_reserved_value or 0)))
    if property.raw_direct_stream is not None:
        value_streams.append(MsgStream(_value_stream_name(property.property_id, property.property_type), bytes(property.raw_direct_stream)))
    for index, payload in property.raw_indexed_streams:
        value_streams.append(MsgStream(_indexed_value_stream_name(property.property_id, property.property_type, index), bytes(payload)))


def _decode_property_entry_value(
    property_type: int,
    inline_value: bytes,
    direct_stream: bytes | None,
    indexed_streams: dict[int, bytes] | None,
    *,
    unicode_strings: bool,
) -> Any:
    if property_type in _FIXED_INLINE_SIZES:
        return _decode_inline_value(property_type, inline_value)
    if property_type in _MULTI_FIXED_BASE_TYPES:
        return _decode_multi_fixed_value(property_type, direct_stream or b"")
    if property_type in _MULTI_VARIABLE_BASE_TYPES:
        ordered = [payload for _, payload in sorted((indexed_streams or {}).items())]
        return _decode_multi_variable_value(property_type, ordered, unicode_strings=unicode_strings)
    if property_type == int(PropertyTypeCode.PTYP_STRING):
        return _decode_unicode_string(direct_stream or b"")
    if property_type == int(PropertyTypeCode.PTYP_STRING8):
        return _decode_string8(direct_stream or b"", unicode_strings=unicode_strings)
    if property_type == int(PropertyTypeCode.PTYP_BINARY):
        return bytes(direct_stream or b"")
    if property_type == int(PropertyTypeCode.PTYP_GUID):
        payload = direct_stream or b""
        return uuid.UUID(bytes_le=payload) if len(payload) == 16 else bytes(payload)
    if property_type == int(PropertyTypeCode.PTYP_OBJECT):
        return None
    return bytes(direct_stream or inline_value)


def _encode_stream_property(
    property: MapiProperty, *, role: str, attachment_method: int | None
) -> tuple[list[tuple[str, bytes]], int, int]:
    property_id = property.property_id
    property_type = property.property_type
    stream_payloads: list[tuple[str, bytes]] = []

    if property_type in _MULTI_FIXED_BASE_TYPES:
        payload = _encode_multi_fixed_value(property_type, property.value)
        stream_payloads.append((_value_stream_name(property_id, property_type), payload))
        return stream_payloads, len(payload), 0

    if property_type in _MULTI_VARIABLE_BASE_TYPES:
        values = list(property.value or [])
        length_entries = bytearray()
        for index, value in enumerate(values):
            payload = _encode_single_stream_value(
                _MULTI_VARIABLE_BASE_TYPES[property_type],
                value,
                include_null_terminator=True,
            )
            stream_payloads.append((_indexed_value_stream_name(property_id, property_type, index), payload))
            if property_type == int(PropertyTypeCode.PTYP_MULTIPLE_BINARY):
                length_entries.extend(struct.pack("<II", len(payload), 0))
            else:
                length_entries.extend(struct.pack("<I", len(payload)))
        stream_payloads.insert(0, (_value_stream_name(property_id, property_type), bytes(length_entries)))
        return stream_payloads, len(length_entries), 0

    if property_type == int(PropertyTypeCode.PTYP_OBJECT):
        reserved_value = 0
        attach_method = attachment_method or ATTACH_METHOD_BY_VALUE
        if role == ATTACHMENT_ROLE and attach_method == ATTACH_METHOD_EMBEDDED:
            reserved_value = 0x01
        elif role == ATTACHMENT_ROLE and attach_method == ATTACH_METHOD_STORAGE:
            reserved_value = 0x04
        return stream_payloads, 0xFFFFFFFF, reserved_value

    payload = _encode_single_stream_value(property_type, property.value, include_null_terminator=False)
    stream_payloads.append((_value_stream_name(property_id, property_type), payload))
    size_value = len(payload)
    if property_type == int(PropertyTypeCode.PTYP_STRING):
        size_value += 2
    elif property_type == int(PropertyTypeCode.PTYP_STRING8):
        size_value += 1
    return stream_payloads, size_value, 0


def _encode_inline_value(property_type: int, value: Any) -> bytes:
    if property_type == int(PropertyTypeCode.PTYP_INTEGER16):
        return struct.pack("<h", int(value)).ljust(8, b"\x00")
    if property_type == int(PropertyTypeCode.PTYP_INTEGER32):
        return struct.pack("<i", int(value)).ljust(8, b"\x00")
    if property_type == int(PropertyTypeCode.PTYP_FLOATING32):
        return struct.pack("<f", float(value)).ljust(8, b"\x00")
    if property_type == int(PropertyTypeCode.PTYP_FLOATING64):
        return struct.pack("<d", float(value))
    if property_type == int(PropertyTypeCode.PTYP_CURRENCY):
        return struct.pack("<q", int(value))
    if property_type == int(PropertyTypeCode.PTYP_FLOATINGTIME):
        return struct.pack("<d", float(value))
    if property_type == int(PropertyTypeCode.PTYP_ERRORCODE):
        return struct.pack("<I", int(value)).ljust(8, b"\x00")
    if property_type == int(PropertyTypeCode.PTYP_BOOLEAN):
        return struct.pack("<H", 1 if value else 0).ljust(8, b"\x00")
    if property_type == int(PropertyTypeCode.PTYP_INTEGER64):
        return struct.pack("<q", int(value))
    if property_type == int(PropertyTypeCode.PTYP_TIME):
        return struct.pack("<Q", _datetime_to_filetime(value))
    raise MsgError(f"Unsupported fixed inline property type: 0x{property_type:04X}")


def _decode_inline_value(property_type: int, raw: bytes) -> Any:
    if property_type == int(PropertyTypeCode.PTYP_INTEGER16):
        return struct.unpack_from("<h", raw.ljust(2, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_INTEGER32):
        return struct.unpack_from("<i", raw.ljust(4, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_FLOATING32):
        return struct.unpack_from("<f", raw.ljust(4, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_FLOATING64):
        return struct.unpack_from("<d", raw.ljust(8, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_CURRENCY):
        return struct.unpack_from("<q", raw.ljust(8, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_FLOATINGTIME):
        return struct.unpack_from("<d", raw.ljust(8, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_ERRORCODE):
        return struct.unpack_from("<I", raw.ljust(4, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_BOOLEAN):
        return struct.unpack_from("<H", raw.ljust(2, b"\x00"), 0)[0] != 0
    if property_type == int(PropertyTypeCode.PTYP_INTEGER64):
        return struct.unpack_from("<q", raw.ljust(8, b"\x00"), 0)[0]
    if property_type == int(PropertyTypeCode.PTYP_TIME):
        return _filetime_to_datetime(struct.unpack_from("<Q", raw.ljust(8, b"\x00"), 0)[0])
    return raw


def _encode_single_stream_value(property_type: int, value: Any, *, include_null_terminator: bool) -> bytes:
    if property_type == int(PropertyTypeCode.PTYP_STRING):
        payload = (value or "").encode("utf-16-le")
        return payload + (b"\x00\x00" if include_null_terminator else b"")
    if property_type == int(PropertyTypeCode.PTYP_STRING8):
        payload = _encode_string8(value)
        return payload + (b"\x00" if include_null_terminator else b"")
    if property_type == int(PropertyTypeCode.PTYP_BINARY):
        return bytes(value or b"")
    if property_type == int(PropertyTypeCode.PTYP_GUID):
        if isinstance(value, bytes):
            return bytes(value)
        return _coerce_uuid(value).bytes_le
    if property_type == int(PropertyTypeCode.PTYP_OBJECT):
        return bytes(value or b"")
    return bytes(value or b"")


def _decode_multi_fixed_value(property_type: int, payload: bytes) -> list[Any]:
    base_type = _MULTI_FIXED_BASE_TYPES[property_type]
    item_size = 16 if base_type == int(PropertyTypeCode.PTYP_GUID) else _FIXED_INLINE_SIZES[base_type]
    values = []
    for offset in range(0, len(payload), item_size):
        chunk = payload[offset : offset + item_size]
        if len(chunk) < item_size:
            break
        if base_type == int(PropertyTypeCode.PTYP_GUID):
            values.append(uuid.UUID(bytes_le=chunk))
        elif base_type == int(PropertyTypeCode.PTYP_FLOATING32):
            values.append(struct.unpack("<f", chunk)[0])
        elif base_type == int(PropertyTypeCode.PTYP_FLOATING64):
            values.append(struct.unpack("<d", chunk)[0])
        elif base_type == int(PropertyTypeCode.PTYP_CURRENCY):
            values.append(struct.unpack("<q", chunk)[0])
        elif base_type == int(PropertyTypeCode.PTYP_FLOATINGTIME):
            values.append(struct.unpack("<d", chunk)[0])
        elif base_type == int(PropertyTypeCode.PTYP_INTEGER16):
            values.append(struct.unpack("<h", chunk)[0])
        elif base_type == int(PropertyTypeCode.PTYP_INTEGER32):
            values.append(struct.unpack("<i", chunk)[0])
        elif base_type == int(PropertyTypeCode.PTYP_INTEGER64):
            values.append(struct.unpack("<q", chunk)[0])
        elif base_type == int(PropertyTypeCode.PTYP_TIME):
            values.append(_filetime_to_datetime(struct.unpack("<Q", chunk)[0]))
    return values


def _encode_multi_fixed_value(property_type: int, values: Iterable[Any]) -> bytes:
    base_type = _MULTI_FIXED_BASE_TYPES[property_type]
    payload = bytearray()
    for value in values or []:
        if base_type == int(PropertyTypeCode.PTYP_GUID):
            if isinstance(value, bytes):
                payload.extend(bytes(value))
                continue
            payload.extend(_coerce_uuid(value).bytes_le)
        else:
            payload.extend(_encode_inline_value(base_type, value)[: _FIXED_INLINE_SIZES[base_type]])
    return bytes(payload)


def _decode_multi_variable_value(property_type: int, values: list[bytes], *, unicode_strings: bool) -> list[Any]:
    base_type = _MULTI_VARIABLE_BASE_TYPES[property_type]
    if base_type == int(PropertyTypeCode.PTYP_STRING):
        return [_decode_unicode_string(value) for value in values]
    if base_type == int(PropertyTypeCode.PTYP_STRING8):
        return [_decode_string8(value, unicode_strings=unicode_strings) for value in values]
    return [bytes(value) for value in values]


def _detect_unicode_state(storage: MsgStorage) -> bool:
    prop_stream = storage.find_stream(PROPERTY_STREAM_NAME)
    if prop_stream is None:
        return True
    try:
        _, entries = MsgReader.parse_top_level_property_stream(prop_stream.data)
    except MsgError:
        return True
    target_tag = (int(CommonMessagePropertyId.STORE_SUPPORT_MASK) << 16) | int(PropertyTypeCode.PTYP_INTEGER32)
    for entry in entries:
        if entry.property_tag == target_tag:
            return (struct.unpack_from("<I", entry.value, 0)[0] & STORE_UNICODE_OK) != 0
    for stream in storage.streams:
        match = _STREAM_PROP_RE.match(stream.name)
        if match is not None and int(match.group(2), 16) == int(PropertyTypeCode.PTYP_STRING):
            return True
    return False


def _clone_msg_storage(storage: MsgStorage) -> MsgStorage:
    return MsgStorage(
        name=storage.name,
        role=storage.role,
        clsid=storage.clsid,
        state_bits=storage.state_bits,
        creation_time=storage.creation_time,
        modified_time=storage.modified_time,
        streams=[_clone_msg_stream(stream) for stream in storage.streams],
        storages=[_clone_msg_storage(child) for child in storage.storages],
    )


def _clone_msg_stream(stream: MsgStream) -> MsgStream:
    return MsgStream(
        name=stream.name,
        data=bytes(stream.data),
        clsid=stream.clsid,
        state_bits=stream.state_bits,
        creation_time=stream.creation_time,
        modified_time=stream.modified_time,
    )


def _value_stream_name(property_id: int, property_type: int) -> str:
    return f"{PROPERTY_VALUE_STREAM_PREFIX}{property_id:04X}{property_type:04X}"


def _indexed_value_stream_name(property_id: int, property_type: int, index: int) -> str:
    return f"{PROPERTY_VALUE_STREAM_PREFIX}{property_id:04X}{property_type:04X}-{index:08X}"


def _mapping_stream_id(value: int, guid_index: int, kind_bit: int) -> int:
    if kind_bit == 0:
        return 0x1000 + ((value ^ (guid_index << 1)) % 0x1F)
    return 0x1000 + ((value ^ ((guid_index << 1) | 1)) % 0x1F)


def _crc32_utf16(text: str) -> int:
    return binascii.crc32(text.encode("utf-16-le")) & 0xFFFFFFFF


def _datetime_to_filetime(value: Any) -> int:
    if value is None:
        return 0
    if not isinstance(value, datetime):
        raise MsgError(f"Expected datetime for PTYP_TIME, got {type(value)!r}")
    utc_value = value.astimezone(UTC)
    delta = utc_value - datetime(1601, 1, 1, tzinfo=UTC)
    return int(delta.total_seconds() * 10_000_000)


def _filetime_to_datetime(value: int) -> datetime | None:
    if value == 0:
        return None
    try:
        return datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=value / 10)
    except OverflowError:
        return value


def _decode_unicode_string(data: bytes) -> str:
    return data.decode("utf-16-le", errors="replace").rstrip("\x00")


def _decode_string8(data: bytes, *, unicode_strings: bool) -> str:
    encoding = "cp1252" if not unicode_strings else "utf-8"
    try:
        return data.decode(encoding, errors="replace").rstrip("\x00")
    except LookupError:
        return data.decode("cp1252", errors="replace").rstrip("\x00")


def _encode_string8(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return str(value or "").encode("cp1252", errors="replace")


def _null_terminator_size(property_type: int) -> int:
    if property_type == int(PropertyTypeCode.PTYP_STRING):
        return 2
    if property_type == int(PropertyTypeCode.PTYP_STRING8):
        return 1
    return 0


def _object_reserved_marker(property: MapiProperty) -> int:
    if property.property_id == int(CommonMessagePropertyId.ATTACH_DATA_BINARY):
        return ATTACH_METHOD_EMBEDDED if property.property_type == int(PropertyTypeCode.PTYP_OBJECT) else ATTACH_METHOD_BY_VALUE
    return ATTACH_METHOD_BY_VALUE
