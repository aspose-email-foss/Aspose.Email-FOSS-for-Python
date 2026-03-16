from __future__ import annotations

import datetime
import struct
import sys
import unittest
from email.message import EmailMessage
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from aspose.email_foss import cfb as branded_cfb
from aspose.email_foss import msg as branded_msg
from aspose.email_foss.cfb import CFBReader, CFBStorage, CFBStream, CFBWriter, CFBDocument, ROOT_ENTRY_NAME
from aspose.email_foss.msg import (
    ATTACHMENT_ROLE,
    EMBEDDED_MESSAGE_ROLE,
    MESSAGE_ROLE,
    NAMED_PROPERTY_MAPPING_STORAGE_NAME,
    NAMED_PROPERTY_MAPPING_ROLE,
    PROPERTY_STREAM_NAME,
    ATTACH_METHOD_EMBEDDED,
    MapiMessage,
    MapiNamedProperty,
    MsgDocument,
    MsgError,
    MsgReader,
    MsgStorage,
    MsgStream,
    MsgWriter,
    PS_PUBLIC_STRINGS,
    PropertyId,
    PropertyTypeCode,
)
from aspose.email_foss.msg.property_tags import CommonMessagePropertyId


class TestMsgFormats(unittest.TestCase):
    def test_branded_namespace_exports_publishable_modules(self) -> None:
        self.assertIs(branded_msg.MapiMessage, MapiMessage)
        self.assertIs(branded_msg.MsgReader, MsgReader)
        self.assertIs(branded_msg.MsgWriter, MsgWriter)
        self.assertIs(branded_msg.PropertyId, PropertyId)
        self.assertIs(branded_cfb.CFBReader, CFBReader)
        self.assertIs(branded_cfb.CFBWriter, CFBWriter)

    def test_manual_top_level_property_stream_parsing(self) -> None:
        property_tag = (int(CommonMessagePropertyId.STORE_SUPPORT_MASK) << 16) | int(PropertyTypeCode.PTYP_INTEGER32)
        entry = struct.pack("<II", property_tag, 0x00000006) + struct.pack("<I", 0x00040000).ljust(8, b"\x00")
        payload = (
            b"\xAA" * 8
            + struct.pack("<I", 5)
            + struct.pack("<I", 7)
            + struct.pack("<I", 1)
            + struct.pack("<I", 2)
            + b"\xBB" * 8
            + entry
        )

        header, entries = MsgReader.parse_top_level_property_stream(payload)

        self.assertEqual(header.reserved_0, b"\xAA" * 8)
        self.assertEqual(header.next_recipient_id, 5)
        self.assertEqual(header.next_attachment_id, 7)
        self.assertEqual(header.recipient_count, 1)
        self.assertEqual(header.attachment_count, 2)
        self.assertEqual(header.reserved_1, b"\xBB" * 8)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].property_tag, property_tag)
        self.assertEqual(entries[0].flags, 0x00000006)
        self.assertEqual(struct.unpack_from("<I", entries[0].value, 0)[0], 0x00040000)

    def test_property_stream_parsers_reject_misaligned_payloads(self) -> None:
        with self.assertRaises(MsgError):
            MsgReader.parse_top_level_property_stream(b"\x00" * 33)
        with self.assertRaises(MsgError):
            MsgReader.parse_subobject_property_stream_data(b"\x00" * 9)
        with self.assertRaises(MsgError):
            MsgReader.parse_subobject_property_stream_data(b"\x00" * 25)

    def test_high_level_message_round_trip_preserves_core_msg_structure(self) -> None:
        message = MapiMessage.create("Hello", "Body")
        message.add_recipient("alice@example.com", display_name="Alice")
        message.add_attachment("a.txt", b"abc", mime_type="text/plain")
        message.set_named_property(
            MapiNamedProperty.string("Keywords", PS_PUBLIC_STRINGS),
            PropertyTypeCode.PTYP_MULTIPLE_STRING8,
            ["one", "two"],
        )

        reader = MsgReader(CFBReader(message.to_bytes()))
        document = MsgDocument.from_reader(reader)
        round_tripped = MapiMessage.from_msg_document(document)

        self.assertEqual(reader.top_level_header.recipient_count, 1)
        self.assertEqual(reader.top_level_header.attachment_count, 1)
        self.assertEqual(len(tuple(reader.iter_recipient_storages())), 1)
        self.assertEqual(len(tuple(reader.iter_attachment_storages())), 1)

        nameid_storage = reader.storage_layout.named_property_mapping_storage
        nameid_stream_names = {
            child.name for child in reader.cfb_reader.iter_children(nameid_storage.stream_id) if child.is_stream()
        }
        self.assertIn("__substg1.0_00020102", nameid_stream_names)
        self.assertIn("__substg1.0_00030102", nameid_stream_names)
        self.assertIn("__substg1.0_00040102", nameid_stream_names)

        recipient_entry = next(reader.iter_recipient_storages())
        attachment_entry = next(reader.iter_attachment_storages())
        _, recipient_props = reader.parse_subobject_property_stream(recipient_entry.stream_id)
        _, attachment_props = reader.parse_subobject_property_stream(attachment_entry.stream_id)
        self.assertGreater(len(recipient_props), 0)
        self.assertGreater(len(attachment_props), 0)

        named = round_tripped.get_named_property(
            MapiNamedProperty.string("Keywords", PS_PUBLIC_STRINGS),
            int(PropertyTypeCode.PTYP_MULTIPLE_STRING8),
        )
        self.assertEqual(round_tripped.subject, "Hello")
        self.assertEqual(round_tripped.body, "Body")
        self.assertEqual(len(round_tripped.recipients), 1)
        self.assertEqual(len(round_tripped.attachments), 1)
        self.assertIsNotNone(named)
        assert named is not None
        self.assertEqual(named.value, ["one", "two"])

    def test_embedded_message_attachment_round_trip_produces_embedded_message_storage(self) -> None:
        parent = MapiMessage.create("Outer", "Parent body")
        child = MapiMessage.create("Inner", "Child body")
        parent.add_embedded_message_attachment(child, filename="inner.msg")

        reader = MsgReader(CFBReader(parent.to_bytes()))
        document = MsgDocument.from_reader(reader)
        attachment_storages = [storage for storage in document.root.storages if storage.role == ATTACHMENT_ROLE]

        self.assertEqual(len(attachment_storages), 1)
        embedded = next((storage for storage in attachment_storages[0].storages if storage.role == EMBEDDED_MESSAGE_ROLE), None)
        self.assertIsNotNone(embedded)
        assert embedded is not None
        self.assertEqual(embedded.name, "__substg1.0_3701000D")
        self.assertEqual(embedded.role, EMBEDDED_MESSAGE_ROLE)
        embedded_entry = reader.cfb_reader.resolve_path(
            ["__attach_version1.0_#00000000", "__substg1.0_3701000D"]
        )
        self.assertIsNotNone(embedded_entry)
        assert embedded_entry is not None
        embedded_header, _ = reader.parse_message_property_stream(embedded_entry.stream_id)
        self.assertEqual(embedded_header.recipient_count, 0)

    def test_reader_rejects_invalid_recipient_storage_name(self) -> None:
        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_storage(CFBStorage(NAMED_PROPERTY_MAPPING_STORAGE_NAME))
        root.add_stream(CFBStream(PROPERTY_STREAM_NAME, _top_level_property_stream(recipient_count=1)))
        invalid_recipient = root.add_storage(CFBStorage("__recip_version1.0_bad"))
        invalid_recipient.add_stream(CFBStream(PROPERTY_STREAM_NAME, _subobject_property_stream()))

        with self.assertRaises(MsgError):
            MsgReader(CFBReader(CFBWriter.to_bytes(CFBDocument(root=root))))

    def test_strict_writer_rejects_named_property_mapping_in_embedded_message(self) -> None:
        root = MsgStorage(name=ROOT_ENTRY_NAME, role=MESSAGE_ROLE)
        root.add_storage(MsgStorage(name=NAMED_PROPERTY_MAPPING_STORAGE_NAME))
        root.add_stream(MsgStream(PROPERTY_STREAM_NAME, _top_level_property_stream(attachment_count=1)))

        attachment = root.add_storage(MsgStorage(name="__attach_version1.0_#00000000", role=ATTACHMENT_ROLE))
        attachment.add_stream(MsgStream(PROPERTY_STREAM_NAME, _attachment_property_stream()))

        embedded = attachment.add_storage(MsgStorage(name="__substg1.0_3701000D", role=EMBEDDED_MESSAGE_ROLE))
        embedded.add_stream(MsgStream(PROPERTY_STREAM_NAME, _top_level_property_stream()))
        embedded.add_storage(MsgStorage(name=NAMED_PROPERTY_MAPPING_STORAGE_NAME))

        with self.assertRaises(MsgError):
            MsgWriter.to_bytes(MsgDocument(root=root, strict=True))

    def test_email_message_conversion_round_trip(self) -> None:
        email_message = EmailMessage()
        email_message["Subject"] = "Converted"
        email_message["From"] = "Alice <alice@example.com>"
        email_message["To"] = "Bob <bob@example.com>"
        email_message["Message-ID"] = "<id@example.com>"
        email_message.set_content("Plain body")
        email_message.add_alternative("<p>HTML body</p>", subtype="html")
        email_message.add_attachment(b"payload", maintype="application", subtype="octet-stream", filename="a.bin")

        message = MapiMessage.from_email_message(email_message)
        projected = message.to_email_message()

        self.assertEqual(message.subject, "Converted")
        self.assertEqual(len(message.recipients), 1)
        self.assertEqual(len(message.attachments), 1)
        self.assertEqual(projected["Subject"], "Converted")
        self.assertEqual(projected["Message-ID"], "<id@example.com>")
        self.assertTrue(projected.is_multipart())

    def test_readme_quick_start_round_trip(self) -> None:
        message = MapiMessage.create("Hello", "Body")
        message.set_property(PropertyId.SENDER_NAME, "Build Agent")
        message.set_property(PropertyId.SENDER_EMAIL_ADDRESS, "build.agent@example.com")
        message.set_property(
            PropertyId.MESSAGE_DELIVERY_TIME,
            datetime.datetime(2026, 3, 15, 10, 30, tzinfo=datetime.timezone.utc),
        )
        message.add_recipient("alice@example.com", display_name="Alice Example")
        message.add_attachment("hello.txt", b"sample attachment\n", mime_type="text/plain")

        loaded = MapiMessage.from_msg_document(MsgDocument.from_reader(MsgReader(CFBReader(message.to_bytes()))))
        email_message = loaded.to_email_message()

        self.assertEqual(email_message["Subject"], "Hello")
        self.assertEqual(email_message["From"], "Build Agent <build.agent@example.com>")
        self.assertEqual(email_message["To"], "Alice Example <alice@example.com>")

    def test_high_level_property_api_accepts_common_message_property_id(self) -> None:
        message = MapiMessage.create()
        message.set_property(CommonMessagePropertyId.SUBJECT, PropertyTypeCode.PTYP_STRING, "Enum subject")

        property_object = message.get_property(CommonMessagePropertyId.SUBJECT, int(PropertyTypeCode.PTYP_STRING))
        property_value = message.get_property_value(CommonMessagePropertyId.SUBJECT)

        self.assertIsNotNone(property_object)
        assert property_object is not None
        self.assertEqual(property_object.property_id, int(CommonMessagePropertyId.SUBJECT))
        self.assertEqual(property_object.value, "Enum subject")
        self.assertEqual(property_value, "Enum subject")

    def test_high_level_property_api_accepts_typed_property_id_short_form(self) -> None:
        message = MapiMessage.create()
        delivery_time = datetime.datetime(2026, 3, 15, 10, 30, tzinfo=datetime.timezone.utc)
        message.set_property(PropertyId.SUBJECT, "Typed subject")
        message.set_property(PropertyId.MESSAGE_DELIVERY_TIME, delivery_time)

        subject_property = message.get_property(PropertyId.SUBJECT)
        subject_value = message.get_property_value(PropertyId.SUBJECT)
        time_property = message.get_property(PropertyId.MESSAGE_DELIVERY_TIME)
        time_value = message.get_property_value(PropertyId.MESSAGE_DELIVERY_TIME)

        self.assertIsNotNone(subject_property)
        self.assertIsNotNone(time_property)
        assert subject_property is not None
        assert time_property is not None
        self.assertEqual(subject_property.property_id, int(PropertyId.SUBJECT))
        self.assertEqual(subject_property.property_type, int(PropertyId.SUBJECT.property_type))
        self.assertEqual(subject_value, "Typed subject")
        self.assertEqual(time_property.property_type, int(PropertyId.MESSAGE_DELIVERY_TIME.property_type))
        self.assertEqual(time_value, delivery_time)

    def test_new_messages_emit_minimal_outlook_compatibility_defaults(self) -> None:
        message = MapiMessage.create("Hello", "Body")
        message.set_property(PropertyId.SENDER_EMAIL_ADDRESS, "sender@example.com")
        message.add_recipient("alice@example.com", display_name="Alice")
        message.add_recipient("bob@example.com", display_name="Bob", recipient_type=2)
        message.add_attachment("a.txt", b"abc", mime_type="text/plain")
        round_tripped = MapiMessage.from_msg_document(MsgDocument.from_reader(MsgReader(CFBReader(message.to_bytes()))))

        self.assertEqual(round_tripped.message_class, "IPM.Note")
        self.assertEqual(
            round_tripped.get_property_value(PropertyId.SENDER_ADDRESS_TYPE),
            "SMTP",
        )
        self.assertEqual(round_tripped.get_property_value(PropertyId.MESSAGE_FLAGS), 17)
        self.assertEqual(round_tripped.get_property_value(PropertyId.DISPLAY_TO), "Alice <alice@example.com>")
        self.assertEqual(round_tripped.get_property_value(PropertyId.DISPLAY_CC), "Bob <bob@example.com>")
        self.assertEqual(round_tripped.get_property_value(PropertyId.INTERNET_CODEPAGE), 20127)
        self.assertIsInstance(round_tripped.get_property_value(0x0071), bytes)
        self.assertEqual(round_tripped.get_property_value(0x3016), True)
        self.assertIsInstance(round_tripped.get_property_value(0x300B), bytes)
        self.assertEqual(round_tripped.recipients[0].properties.get(0x3000).value, 0)
        self.assertIsInstance(round_tripped.recipients[0].properties.get(0x0FF6).value, bytes)
        self.assertEqual(round_tripped.attachments[0].properties.get(0x0FF4).value, 2)
        self.assertEqual(round_tripped.attachments[0].properties.get(0x0FF7).value, 0)

    def test_loaded_messages_do_not_gain_new_defaults_on_save(self) -> None:
        root = MsgStorage(name=ROOT_ENTRY_NAME, role=MESSAGE_ROLE)
        root.add_storage(MsgStorage(name=NAMED_PROPERTY_MAPPING_STORAGE_NAME, role=NAMED_PROPERTY_MAPPING_ROLE))
        root.add_stream(MsgStream(PROPERTY_STREAM_NAME, _top_level_property_stream()))
        source = MapiMessage.from_msg_document(MsgDocument(root=root))
        reread = MapiMessage.from_msg_document(MsgDocument.from_reader(MsgReader(CFBReader(source.to_bytes()))))

        self.assertIsNone(reread.get_property_value(PropertyId.MESSAGE_CLASS))
        self.assertIsNone(reread.get_property_value(PropertyId.SENDER_ADDRESS_TYPE))


def _top_level_property_stream(*, recipient_count: int = 0, attachment_count: int = 0) -> bytes:
    return (
        b"\x00" * 8
        + struct.pack("<I", recipient_count if recipient_count else 0)
        + struct.pack("<I", attachment_count if attachment_count else 0)
        + struct.pack("<I", recipient_count)
        + struct.pack("<I", attachment_count)
        + b"\x00" * 8
    )


def _subobject_property_stream() -> bytes:
    return b"\x00" * 8


def _attachment_property_stream() -> bytes:
    property_tag = (int(CommonMessagePropertyId.ATTACH_METHOD) << 16) | int(PropertyTypeCode.PTYP_INTEGER32)
    entry = struct.pack("<II", property_tag, 0x00000006) + struct.pack("<I", ATTACH_METHOD_EMBEDDED).ljust(8, b"\x00")
    return b"\x00" * 8 + entry


if __name__ == "__main__":
    unittest.main()
