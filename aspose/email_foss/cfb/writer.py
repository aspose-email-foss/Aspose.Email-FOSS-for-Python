from __future__ import annotations

import struct
from dataclasses import dataclass, field
from functools import cmp_to_key
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .reader import CFBError, CFBReader
from .types import (
    BYTE_ORDER_LITTLE_ENDIAN,
    MINI_STREAM_CUTOFF_SIZE,
    NOSTREAM,
    ROOT_ENTRY_NAME,
    DirectoryColorFlag,
    DirectoryObjectType,
    FileTime,
    SectorMarker,
)


_ZERO_CLSID = b"\x00" * 16


@dataclass
class CFBStream:
    """Mutable stream node used by the CFB writer."""

    name: str
    data: bytes = b""
    clsid: bytes = _ZERO_CLSID
    state_bits: int = 0
    creation_time: FileTime = FileTime(0)
    modified_time: FileTime = FileTime(0)


@dataclass
class CFBStorage:
    """Mutable storage node used by the CFB writer."""

    name: str
    clsid: bytes = _ZERO_CLSID
    state_bits: int = 0
    creation_time: FileTime = FileTime(0)
    modified_time: FileTime = FileTime(0)
    children: list["CFBStorage | CFBStream"] = field(default_factory=list)

    def add_storage(self, storage: "CFBStorage") -> "CFBStorage":
        self.children.append(storage)
        return storage

    def add_stream(self, stream: CFBStream) -> CFBStream:
        self.children.append(stream)
        return stream


@dataclass
class CFBDocument:
    """Mutable Compound File Binary (CFB) document description."""

    root: CFBStorage
    major_version: int = 3
    minor_version: int = 0x003E
    transaction_signature_number: int = 0

    @classmethod
    def from_reader(cls, reader: CFBReader) -> "CFBDocument":
        def build_storage(entry_id: int) -> CFBStorage:
            entry = reader.get_entry(entry_id)
            storage = CFBStorage(
                name=entry.name,
                clsid=bytes(entry.clsid),
                state_bits=entry.state_bits,
                creation_time=entry.creation_time,
                modified_time=entry.modified_time,
            )
            for child in reader.iter_children(entry.stream_id):
                if child.is_storage():
                    storage.children.append(build_storage(int(child.stream_id)))
                elif child.is_stream():
                    storage.children.append(
                        CFBStream(
                            name=child.name,
                            data=reader.get_stream_data(child.stream_id),
                            clsid=bytes(child.clsid),
                            state_bits=child.state_bits,
                            creation_time=child.creation_time,
                            modified_time=child.modified_time,
                        )
                    )
            return storage

        return cls(
            root=build_storage(0),
            major_version=reader.header.major_version,
            minor_version=reader.header.minor_version,
            transaction_signature_number=reader.header.transaction_signature_number,
        )

    @classmethod
    def from_file(cls, path: Path | str) -> "CFBDocument":
        with CFBReader.from_file(path) as reader:
            return cls.from_reader(reader)


def compare_directory_entry_names(left: str, right: str) -> int:
    """Compare names using the [MS-CFB] sibling ordering rules."""

    left_len = _directory_entry_name_length(left)
    right_len = _directory_entry_name_length(right)
    if left_len != right_len:
        return -1 if left_len < right_len else 1

    for left_char, right_char in zip(left, right):
        left_ord = ord(_simple_uppercase_code_point(left_char))
        right_ord = ord(_simple_uppercase_code_point(right_char))
        if left_ord != right_ord:
            return -1 if left_ord < right_ord else 1

    return 0


class CFBWriter:
    """Deterministic serializer for Compound File Binary (CFB) containers."""

    @classmethod
    def to_bytes(cls, document: CFBDocument) -> bytes:
        return _CFBSerializer(document).serialize()

    @classmethod
    def write_file(cls, document: CFBDocument, path: Path | str) -> None:
        Path(path).write_bytes(cls.to_bytes(document))


@dataclass
class _EntryRecord:
    stream_id: int
    name: str
    object_type: DirectoryObjectType
    clsid: bytes
    state_bits: int
    creation_time: int
    modified_time: int
    stream_data: bytes = b""
    children: list["_EntryRecord"] = field(default_factory=list)
    color_flag: DirectoryColorFlag = DirectoryColorFlag.BLACK
    left_sibling_id: int = NOSTREAM
    right_sibling_id: int = NOSTREAM
    child_id: int = NOSTREAM
    starting_sector_location: int = NOSTREAM
    stream_size: int = 0

    @property
    def is_root(self) -> bool:
        return self.object_type == DirectoryObjectType.ROOT_STORAGE_OBJECT

    @property
    def is_storage(self) -> bool:
        return self.object_type in (DirectoryObjectType.ROOT_STORAGE_OBJECT, DirectoryObjectType.STORAGE_OBJECT)

    @property
    def is_stream(self) -> bool:
        return self.object_type == DirectoryObjectType.STREAM_OBJECT


@dataclass
class _Chain:
    payload: bytes
    sectors: list[int] = field(default_factory=list)

    @property
    def sector_count(self) -> int:
        return len(self.sectors)

    @property
    def first_sector(self) -> int:
        return self.sectors[0] if self.sectors else SectorMarker.ENDOFCHAIN


class _CFBSerializer:
    def __init__(self, document: CFBDocument) -> None:
        self.document = document
        self.major_version = document.major_version
        if self.major_version not in (3, 4):
            raise CFBError(f"Unsupported CFB writer major version: {self.major_version}")
        self.minor_version = document.minor_version
        self.sector_size = 512 if self.major_version == 3 else 4096
        self.mini_sector_size = 64
        self.entries_per_fat_sector = self.sector_size // 4
        self.entries_per_difat_sector = self.entries_per_fat_sector - 1
        self.directory_entries_per_sector = self.sector_size // 128

    def serialize(self) -> bytes:
        root = self.document.root
        if root.name != ROOT_ENTRY_NAME:
            raise CFBError(f"Root storage name must be {ROOT_ENTRY_NAME!r}.")

        records = self._build_entry_records(root)
        self._assign_sibling_trees(records)

        mini_stream_payload, mini_fat_entries = self._plan_mini_stream(records)
        regular_stream_records = [record for record in records if record.is_stream and record.stream_size >= MINI_STREAM_CUTOFF_SIZE]

        regular_chains = {record.stream_id: _Chain(record.stream_data) for record in regular_stream_records}
        root_chain = _Chain(mini_stream_payload)

        directory_payload = self._pack_directory_entries(records)
        directory_chain = _Chain(directory_payload)
        mini_fat_payload = self._pack_u32_array(mini_fat_entries)
        mini_fat_chain = _Chain(mini_fat_payload)

        content_sector_count = (
            sum(self._sector_span_for_payload(chain.payload) for chain in regular_chains.values())
            + self._sector_span_for_payload(root_chain.payload)
            + self._sector_span_for_payload(directory_chain.payload)
            + self._sector_span_for_payload(mini_fat_chain.payload)
        )
        fat_sector_count, difat_sector_count = self._solve_fat_and_difat_sector_counts(content_sector_count)

        next_sector = 0
        for record in regular_stream_records:
            chain = regular_chains[record.stream_id]
            chain.sectors = list(range(next_sector, next_sector + self._sector_span_for_payload(chain.payload)))
            next_sector += chain.sector_count
            record.starting_sector_location = chain.first_sector

        root_chain.sectors = list(range(next_sector, next_sector + self._sector_span_for_payload(root_chain.payload)))
        next_sector += root_chain.sector_count

        directory_chain.sectors = list(range(next_sector, next_sector + self._sector_span_for_payload(directory_chain.payload)))
        next_sector += directory_chain.sector_count

        mini_fat_chain.sectors = list(range(next_sector, next_sector + self._sector_span_for_payload(mini_fat_chain.payload)))
        next_sector += mini_fat_chain.sector_count

        fat_sector_numbers = list(range(next_sector, next_sector + fat_sector_count))
        next_sector += fat_sector_count
        difat_sector_numbers = list(range(next_sector, next_sector + difat_sector_count))
        next_sector += difat_sector_count
        total_sector_count = next_sector

        root_record = records[0]
        root_record.starting_sector_location = root_chain.first_sector
        root_record.stream_size = len(root_chain.payload)
        if root_record.stream_size == 0:
            root_record.starting_sector_location = SectorMarker.ENDOFCHAIN

        if self.major_version == 3 and root_record.stream_size > 0x80000000:
            raise CFBError("Version 3 CFB writer cannot emit mini streams larger than 2 GB.")

        directory_chain.payload = self._pack_directory_entries(records)

        fat_entries = [int(SectorMarker.FREESECT)] * (fat_sector_count * self.entries_per_fat_sector)
        for chain in regular_chains.values():
            self._mark_sector_chain(fat_entries, chain.sectors)
        self._mark_sector_chain(fat_entries, root_chain.sectors)
        self._mark_sector_chain(fat_entries, directory_chain.sectors)
        self._mark_sector_chain(fat_entries, mini_fat_chain.sectors)
        for sector in fat_sector_numbers:
            fat_entries[sector] = int(SectorMarker.FATSECT)
        for sector in difat_sector_numbers:
            fat_entries[sector] = int(SectorMarker.DIFSECT)

        fat_payload = self._pack_u32_array(fat_entries)
        fat_sector_map = self._split_payload(fat_payload, fat_sector_numbers)

        difat_entries = fat_sector_numbers[:]
        header_difat = difat_entries[:109]
        if len(header_difat) < 109:
            header_difat.extend([int(SectorMarker.FREESECT)] * (109 - len(header_difat)))

        difat_payload_map = self._build_difat_sectors(difat_entries[109:], difat_sector_numbers)
        sector_payloads: dict[int, bytes] = {}
        for chain in regular_chains.values():
            sector_payloads.update(self._split_payload(chain.payload, chain.sectors))
        sector_payloads.update(self._split_payload(root_chain.payload, root_chain.sectors))
        sector_payloads.update(self._split_payload(directory_chain.payload, directory_chain.sectors))
        sector_payloads.update(self._split_payload(mini_fat_chain.payload, mini_fat_chain.sectors))
        sector_payloads.update(fat_sector_map)
        sector_payloads.update(difat_payload_map)

        first_directory_sector_location = directory_chain.first_sector
        first_mini_fat_sector_location = mini_fat_chain.first_sector if mini_fat_chain.sectors else int(SectorMarker.ENDOFCHAIN)
        first_difat_sector_location = difat_sector_numbers[0] if difat_sector_numbers else int(SectorMarker.ENDOFCHAIN)
        number_of_directory_sectors = 0 if self.major_version == 3 else len(directory_chain.sectors)
        number_of_mini_fat_sectors = len(mini_fat_chain.sectors)
        number_of_difat_sectors = len(difat_sector_numbers)

        header = self._build_header(
            number_of_directory_sectors=number_of_directory_sectors,
            number_of_fat_sectors=fat_sector_count,
            first_directory_sector_location=first_directory_sector_location,
            first_mini_fat_sector_location=first_mini_fat_sector_location,
            number_of_mini_fat_sectors=number_of_mini_fat_sectors,
            first_difat_sector_location=first_difat_sector_location,
            number_of_difat_sectors=number_of_difat_sectors,
            difat=header_difat,
        )

        out = bytearray()
        out.extend(header)
        for sector_number in range(total_sector_count):
            payload = sector_payloads.get(sector_number, b"")
            out.extend(payload.ljust(self.sector_size, b"\x00"))
        return bytes(out)

    def _build_entry_records(self, root: CFBStorage) -> list[_EntryRecord]:
        records: list[_EntryRecord] = []

        def add_storage(storage: CFBStorage, *, is_root: bool) -> _EntryRecord:
            self._validate_name(storage.name)
            record = _EntryRecord(
                stream_id=len(records),
                name=storage.name,
                object_type=DirectoryObjectType.ROOT_STORAGE_OBJECT if is_root else DirectoryObjectType.STORAGE_OBJECT,
                clsid=self._validate_clsid(storage.clsid),
                state_bits=storage.state_bits,
                creation_time=int(storage.creation_time),
                modified_time=int(storage.modified_time),
            )
            records.append(record)
            sorted_children = self._sorted_children(storage.children)
            for child in sorted_children:
                if isinstance(child, CFBStorage):
                    record.children.append(add_storage(child, is_root=False))
                else:
                    self._validate_name(child.name)
                    child_record = _EntryRecord(
                        stream_id=len(records),
                        name=child.name,
                        object_type=DirectoryObjectType.STREAM_OBJECT,
                        clsid=self._validate_clsid(child.clsid),
                        state_bits=child.state_bits,
                        creation_time=int(child.creation_time),
                        modified_time=int(child.modified_time),
                        stream_data=bytes(child.data),
                        stream_size=len(child.data),
                    )
                    records.append(child_record)
                    record.children.append(child_record)
            return record

        add_storage(root, is_root=True)
        if records[0].name != ROOT_ENTRY_NAME:
            raise CFBError(f"Root storage name must be {ROOT_ENTRY_NAME!r}.")
        return records

    def _assign_sibling_trees(self, records: Sequence[_EntryRecord]) -> None:
        for record in records:
            record.color_flag = DirectoryColorFlag.BLACK
            record.left_sibling_id = NOSTREAM
            record.right_sibling_id = NOSTREAM
            record.child_id = NOSTREAM
        for record in records:
            if record.is_storage and record.children:
                record.child_id = self._build_balanced_sibling_tree(record.children)

    def _build_balanced_sibling_tree(self, children: Sequence[_EntryRecord]) -> int:
        def build(items: Sequence[_EntryRecord]) -> int:
            if not items:
                return NOSTREAM
            mid = len(items) // 2
            record = items[mid]
            record.left_sibling_id = build(items[:mid])
            record.right_sibling_id = build(items[mid + 1 :])
            record.color_flag = DirectoryColorFlag.BLACK
            return record.stream_id

        return build(children)

    def _plan_mini_stream(self, records: Sequence[_EntryRecord]) -> tuple[bytes, list[int]]:
        mini_stream = bytearray()
        mini_fat_entries: list[int] = []
        next_mini_sector = 0

        for record in records:
            if not record.is_stream:
                continue
            if record.stream_size == 0:
                record.starting_sector_location = int(SectorMarker.ENDOFCHAIN)
                continue
            if record.stream_size >= MINI_STREAM_CUTOFF_SIZE:
                continue

            mini_sector_count = self._mini_sector_span_for_size(record.stream_size)
            record.starting_sector_location = next_mini_sector
            for offset in range(mini_sector_count):
                current = next_mini_sector + offset
                next_value = current + 1 if offset + 1 < mini_sector_count else int(SectorMarker.ENDOFCHAIN)
                mini_fat_entries.append(next_value)
            next_mini_sector += mini_sector_count
            mini_stream.extend(record.stream_data.ljust(mini_sector_count * self.mini_sector_size, b"\x00"))

        return bytes(mini_stream), mini_fat_entries

    def _build_header(
        self,
        *,
        number_of_directory_sectors: int,
        number_of_fat_sectors: int,
        first_directory_sector_location: int,
        first_mini_fat_sector_location: int,
        number_of_mini_fat_sectors: int,
        first_difat_sector_location: int,
        number_of_difat_sectors: int,
        difat: Sequence[int],
    ) -> bytes:
        header = bytearray(512)
        header[0:8] = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
        header[8:24] = _ZERO_CLSID
        struct.pack_into("<H", header, 24, self.minor_version)
        struct.pack_into("<H", header, 26, self.major_version)
        struct.pack_into("<H", header, 28, BYTE_ORDER_LITTLE_ENDIAN)
        struct.pack_into("<H", header, 30, 9 if self.major_version == 3 else 12)
        struct.pack_into("<H", header, 32, 6)
        header[34:40] = b"\x00" * 6
        struct.pack_into("<I", header, 40, number_of_directory_sectors)
        struct.pack_into("<I", header, 44, number_of_fat_sectors)
        struct.pack_into("<I", header, 48, first_directory_sector_location)
        struct.pack_into("<I", header, 52, self.document.transaction_signature_number)
        struct.pack_into("<I", header, 56, MINI_STREAM_CUTOFF_SIZE)
        struct.pack_into("<I", header, 60, first_mini_fat_sector_location)
        struct.pack_into("<I", header, 64, number_of_mini_fat_sectors)
        struct.pack_into("<I", header, 68, first_difat_sector_location)
        struct.pack_into("<I", header, 72, number_of_difat_sectors)
        struct.pack_into("<109I", header, 76, *difat)
        return bytes(header).ljust(self.sector_size, b"\x00")

    def _pack_directory_entries(self, records: Sequence[_EntryRecord]) -> bytes:
        total_slots = self._round_up(len(records), self.directory_entries_per_sector)
        payload = bytearray(total_slots * 128)
        for index, record in enumerate(records):
            payload[index * 128 : (index + 1) * 128] = self._pack_directory_entry(record)
        for index in range(len(records), total_slots):
            payload[index * 128 : (index + 1) * 128] = self._pack_unallocated_directory_entry()
        return bytes(payload)

    def _pack_directory_entry(self, record: _EntryRecord) -> bytes:
        data = bytearray(128)
        name_bytes = record.name.encode("utf-16le") + b"\x00\x00"
        if len(name_bytes) > 64:
            raise CFBError(f"Directory entry name is too long: {record.name!r}")
        data[0 : len(name_bytes)] = name_bytes
        struct.pack_into("<H", data, 64, len(name_bytes))
        data[66] = int(record.object_type)
        data[67] = int(record.color_flag)
        struct.pack_into("<I", data, 68, record.left_sibling_id)
        struct.pack_into("<I", data, 72, record.right_sibling_id)
        struct.pack_into("<I", data, 76, record.child_id)

        if record.is_stream:
            clsid = record.clsid
            creation_time = record.creation_time
            modified_time = record.modified_time
            child_id = NOSTREAM
            struct.pack_into("<I", data, 76, child_id)
        else:
            clsid = record.clsid
            creation_time = record.creation_time
            modified_time = record.modified_time

        data[80:96] = clsid
        struct.pack_into("<I", data, 96, record.state_bits)
        struct.pack_into("<Q", data, 100, creation_time)
        struct.pack_into("<Q", data, 108, modified_time)

        if record.object_type == DirectoryObjectType.STORAGE_OBJECT:
            struct.pack_into("<I", data, 116, 0)
            struct.pack_into("<Q", data, 120, 0)
        else:
            starting_sector = record.starting_sector_location
            if record.stream_size == 0 and record.is_stream:
                starting_sector = int(SectorMarker.ENDOFCHAIN)
            struct.pack_into("<I", data, 116, starting_sector)
            stream_size = record.stream_size
            if self.major_version == 3 and stream_size > 0x80000000:
                raise CFBError("Version 3 CFB writer cannot emit streams larger than 2 GB.")
            struct.pack_into("<Q", data, 120, stream_size)

        return bytes(data)

    def _pack_unallocated_directory_entry(self) -> bytes:
        data = bytearray(128)
        struct.pack_into("<I", data, 68, NOSTREAM)
        struct.pack_into("<I", data, 72, NOSTREAM)
        struct.pack_into("<I", data, 76, NOSTREAM)
        return bytes(data)

    def _build_difat_sectors(self, remaining_fat_entries: Sequence[int], difat_sector_numbers: Sequence[int]) -> dict[int, bytes]:
        if not difat_sector_numbers:
            return {}

        sector_map: dict[int, bytes] = {}
        for index, sector_number in enumerate(difat_sector_numbers):
            start = index * self.entries_per_difat_sector
            end = start + self.entries_per_difat_sector
            entries = list(remaining_fat_entries[start:end])
            if len(entries) < self.entries_per_difat_sector:
                entries.extend([int(SectorMarker.FREESECT)] * (self.entries_per_difat_sector - len(entries)))
            next_sector = difat_sector_numbers[index + 1] if index + 1 < len(difat_sector_numbers) else int(SectorMarker.ENDOFCHAIN)
            payload = bytearray(self.sector_size)
            struct.pack_into(f"<{self.entries_per_difat_sector}I", payload, 0, *entries)
            struct.pack_into("<I", payload, self.sector_size - 4, next_sector)
            sector_map[sector_number] = bytes(payload)
        return sector_map

    def _split_payload(self, payload: bytes, sectors: Sequence[int]) -> dict[int, bytes]:
        if not sectors:
            return {}
        chunks: dict[int, bytes] = {}
        for index, sector_number in enumerate(sectors):
            start = index * self.sector_size
            end = start + self.sector_size
            chunks[sector_number] = payload[start:end].ljust(self.sector_size, b"\x00")
        return chunks

    def _pack_u32_array(self, values: Sequence[int]) -> bytes:
        if not values:
            return b""
        padded_len = self._round_up(len(values), self.entries_per_fat_sector)
        padded_values = list(values) + [int(SectorMarker.FREESECT)] * (padded_len - len(values))
        return struct.pack(f"<{len(padded_values)}I", *padded_values)

    def _mark_sector_chain(self, fat_entries: list[int], sectors: Sequence[int]) -> None:
        if not sectors:
            return
        for current, next_sector in zip(sectors, sectors[1:]):
            fat_entries[current] = next_sector
        fat_entries[sectors[-1]] = int(SectorMarker.ENDOFCHAIN)

    def _solve_fat_and_difat_sector_counts(self, content_sector_count: int) -> tuple[int, int]:
        fat_sector_count = 0
        difat_sector_count = 0
        while True:
            total_sector_count = content_sector_count + fat_sector_count + difat_sector_count
            new_fat_sector_count = self._ceil_div(total_sector_count, self.entries_per_fat_sector)
            if new_fat_sector_count <= 109:
                new_difat_sector_count = 0
            else:
                new_difat_sector_count = self._ceil_div(new_fat_sector_count - 109, self.entries_per_difat_sector)
            if new_fat_sector_count == fat_sector_count and new_difat_sector_count == difat_sector_count:
                return fat_sector_count, difat_sector_count
            fat_sector_count = new_fat_sector_count
            difat_sector_count = new_difat_sector_count

    def _sorted_children(self, children: Iterable[CFBStorage | CFBStream]) -> list[CFBStorage | CFBStream]:
        ordered = sorted(children, key=cmp_to_key(lambda left, right: compare_directory_entry_names(left.name, right.name)))
        for left, right in zip(ordered, ordered[1:]):
            if compare_directory_entry_names(left.name, right.name) == 0:
                raise CFBError(f"Duplicate sibling name under CFB comparison rules: {left.name!r} vs {right.name!r}")
        return ordered

    def _validate_name(self, name: str) -> None:
        if not name:
            raise CFBError("CFB writer does not support empty directory entry names.")
        if "\x00" in name:
            raise CFBError("CFB directory entry names must not contain embedded null characters.")
        if _directory_entry_name_length(name) > 64:
            raise CFBError(f"CFB directory entry name exceeds 64-byte field: {name!r}")

    def _validate_clsid(self, clsid: bytes) -> bytes:
        value = bytes(clsid)
        if len(value) != 16:
            raise CFBError(f"CLSID must be exactly 16 bytes, got {len(value)}.")
        return value

    def _sector_span_for_payload(self, payload: bytes) -> int:
        return self._ceil_div(len(payload), self.sector_size)

    def _mini_sector_span_for_size(self, size: int) -> int:
        return self._ceil_div(size, self.mini_sector_size)

    def _ceil_div(self, value: int, divisor: int) -> int:
        if value <= 0:
            return 0
        return (value + divisor - 1) // divisor

    def _round_up(self, value: int, alignment: int) -> int:
        if value == 0:
            return 0
        return ((value + alignment - 1) // alignment) * alignment


def _directory_entry_name_length(name: str) -> int:
    return len(name.encode("utf-16le")) + 2


def _simple_uppercase_code_point(value: str) -> str:
    upper = value.upper()
    return upper if len(upper) == 1 else value
