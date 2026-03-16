from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from aspose.email_foss.cfb import CFBError, CFBDocument, CFBReader, CFBStorage, CFBStream, CFBWriter, ROOT_ENTRY_NAME


class TestCFBFormats(unittest.TestCase):
    def test_v3_round_trip_routes_small_streams_through_mini_stream(self) -> None:
        small_payload = b"mini-stream-payload"
        large_payload = (b"0123456789ABCDEF" * 400)

        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("Small", small_payload))
        nested = root.add_storage(CFBStorage("Nested"))
        nested.add_stream(CFBStream("Large", large_payload))

        reader = CFBReader(CFBWriter.to_bytes(CFBDocument(root=root, major_version=3)))

        self.assertEqual(reader.major_version, 3)
        self.assertEqual(reader.sector_size, 512)
        self.assertEqual(reader.header.number_of_directory_sectors, 0)
        self.assertGreater(len(reader.mini_fat), 0)

        small_entry = reader.resolve_path(["Small"])
        large_entry = reader.resolve_path(["Nested", "Large"])
        self.assertIsNotNone(small_entry)
        self.assertIsNotNone(large_entry)
        assert small_entry is not None
        assert large_entry is not None

        self.assertLess(small_entry.stream_size, reader.header.mini_stream_cutoff_size)
        self.assertGreaterEqual(large_entry.stream_size, reader.header.mini_stream_cutoff_size)
        self.assertEqual(reader.get_stream_data(small_entry.stream_id), small_payload)
        self.assertEqual(reader.get_stream_data(large_entry.stream_id), large_payload)
        self.assertGreater(reader.root_entry.stream_size, 0)

    def test_v4_round_trip_uses_4096_byte_sectors(self) -> None:
        payload = b"A" * 7000

        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("Payload", payload))

        reader = CFBReader(CFBWriter.to_bytes(CFBDocument(root=root, major_version=4)))

        self.assertEqual(reader.major_version, 4)
        self.assertEqual(reader.sector_size, 4096)
        self.assertEqual(reader.mini_sector_size, 64)
        self.assertGreater(reader.header.number_of_directory_sectors, 0)

        stream_entry = reader.resolve_path(["Payload"])
        self.assertIsNotNone(stream_entry)
        assert stream_entry is not None
        self.assertEqual(reader.get_stream_data(stream_entry.stream_id), payload)

    def test_large_v3_document_emits_difat(self) -> None:
        payload = b"Z" * (512 * 15000)

        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("Huge", payload))

        reader = CFBReader(CFBWriter.to_bytes(CFBDocument(root=root, major_version=3)))

        self.assertGreater(reader.header.number_of_fat_sectors, 109)
        self.assertGreater(reader.header.number_of_difat_sectors, 0)
        stream_entry = reader.resolve_path(["Huge"])
        self.assertIsNotNone(stream_entry)
        assert stream_entry is not None
        self.assertEqual(reader.get_stream_data(stream_entry.stream_id), payload)

    def test_writer_rejects_duplicate_sibling_names_under_cfb_comparison_rules(self) -> None:
        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("ab", b"left"))
        root.add_stream(CFBStream("AB", b"right"))

        with self.assertRaises(CFBError):
            CFBWriter.to_bytes(CFBDocument(root=root))

    def test_reader_rejects_invalid_signature_and_byte_order(self) -> None:
        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("Payload", b"abc"))
        payload = bytearray(CFBWriter.to_bytes(CFBDocument(root=root)))

        bad_signature = bytes(b"\x00" + payload[1:])
        with self.assertRaises(CFBError):
            CFBReader(bad_signature)

        struct.pack_into("<H", payload, 0x1C, 0xFEFF)
        with self.assertRaises(CFBError):
            CFBReader(bytes(payload))


if __name__ == "__main__":
    unittest.main()
