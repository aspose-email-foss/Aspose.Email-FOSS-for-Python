from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

from .types import (
    BYTE_ORDER_LITTLE_ENDIAN,
    MAXREGSECT,
    MINI_STREAM_CUTOFF_SIZE,
    NOSTREAM,
    ROOT_STREAM_ID,
    SectorMarker,
    DirectoryColorFlag,
    DirectoryObjectType,
    FileTime,
    SectorNumber,
    StreamId,
)


@dataclass(frozen=True)
class Header:
    """Header record at file offset 0 defining Compound File Binary (CFB) geometry and allocation chain entry points."""

    # Identification signature for the compound file format.
    header_signature: bytes
    # Reserved CLSID field; must be CLSID_NULL in conforming files.
    header_clsid: bytes
    # Minor format revision for non-breaking changes.
    minor_version: int
    # Major format version that determines compatible sector layout rules.
    major_version: int
    # Byte-order marker for integer fields; indicates little-endian encoding.
    byte_order: int
    # Power-of-two exponent used to compute normal sector size.
    sector_shift: int
    # Power-of-two exponent used to compute mini-sector size.
    mini_sector_shift: int
    # Reserved bytes in header, written as zero in conforming files.
    reserved: bytes
    # Count of directory sectors in the file.
    number_of_directory_sectors: int
    # Count of FAT sectors in the file.
    number_of_fat_sectors: int
    # First sector number of the directory stream chain.
    first_directory_sector_location: SectorNumber
    # Transaction sequence value used by transactional implementations.
    transaction_signature_number: int
    # Threshold size below which streams are stored in the mini stream.
    mini_stream_cutoff_size: int
    # First sector number of the mini FAT chain.
    first_mini_fat_sector_location: SectorNumber
    # Count of mini FAT sectors in the file.
    number_of_mini_fat_sectors: int
    # First sector number of the DIFAT chain.
    first_difat_sector_location: SectorNumber
    # Count of DIFAT sectors in the file.
    number_of_difat_sectors: int
    # Initial DIFAT array entries that point to FAT sector locations.
    difat: List[SectorNumber]

    @property
    def sector_size(self) -> int:
        return 1 << self.sector_shift

    @property
    def mini_sector_size(self) -> int:
        return 1 << self.mini_sector_shift


@dataclass(frozen=True)
class DirectoryEntry:
    """Fixed-size directory record for one storage/stream object and its tree links."""

    # Index in the directory entry array (stream ID).
    stream_id: StreamId
    # UTF-16 object name (decoded from fixed-size name field).
    name: str
    # Length in bytes of the name value including UTF-16 null terminator.
    directory_entry_name_length: int
    # Directory object kind (unallocated, storage, stream, or root storage).
    object_type: DirectoryObjectType
    # Red-black tree node color metadata.
    color_flag: DirectoryColorFlag
    # Stream ID pointer to left sibling entry.
    left_sibling_id: StreamId
    # Stream ID pointer to right sibling entry.
    right_sibling_id: StreamId
    # Stream ID pointer to first child of this storage.
    child_id: StreamId
    # CLSID associated with storage/root entries; zero for stream entries.
    clsid: bytes
    # User-defined state flags for storage/root objects.
    state_bits: int
    # FILETIME creation timestamp for storage objects.
    creation_time: FileTime
    # FILETIME modification timestamp for storage objects.
    modified_time: FileTime
    # First sector location of stream data or mini-stream root.
    starting_sector_location: SectorNumber
    # Byte length of stream data.
    stream_size: int

    def is_storage(self) -> bool:
        return self.object_type in (DirectoryObjectType.STORAGE_OBJECT, DirectoryObjectType.ROOT_STORAGE_OBJECT)

    def is_stream(self) -> bool:
        return self.object_type == DirectoryObjectType.STREAM_OBJECT

    def is_root(self) -> bool:
        return self.object_type == DirectoryObjectType.ROOT_STORAGE_OBJECT


class CFBError(Exception):
    """Raised for malformed or unsupported Compound File Binary (CFB) content."""


class CFBReader:
    """Reusable reader for Compound File Binary (CFB) containers.

    Notes:
    - This class does not print directly. Use iterator and property APIs.
    - Stream data is materialized lazily on first `get_stream_data` access.
    """

    HEADER_LAYOUT: Dict[str, Tuple[int, int]] = {
        "header_signature": (0x0000, 8),
        "header_clsid": (0x0008, 16),
        "minor_version": (0x0018, 2),
        "major_version": (0x001A, 2),
        "byte_order": (0x001C, 2),
        "sector_shift": (0x001E, 2),
        "mini_sector_shift": (0x0020, 2),
        "reserved": (0x0022, 6),
        "number_of_directory_sectors": (0x0028, 4),
        "number_of_fat_sectors": (0x002C, 4),
        "first_directory_sector_location": (0x0030, 4),
        "transaction_signature_number": (0x0034, 4),
        "mini_stream_cutoff_size": (0x0038, 4),
        "first_mini_fat_sector_location": (0x003C, 4),
        "number_of_mini_fat_sectors": (0x0040, 4),
        "first_difat_sector_location": (0x0044, 4),
        "number_of_difat_sectors": (0x0048, 4),
        "difat": (0x004C, 436),
    }

    DIRECTORY_ENTRY_LAYOUT: Dict[str, Tuple[int, int]] = {
        "directory_entry_name": (0, 64),
        "directory_entry_name_length": (64, 2),
        "object_type": (66, 1),
        "color_flag": (67, 1),
        "left_sibling_id": (68, 4),
        "right_sibling_id": (72, 4),
        "child_id": (76, 4),
        "clsid": (80, 16),
        "state_bits": (96, 4),
        "creation_time": (100, 8),
        "modified_time": (108, 8),
        "starting_sector_location": (116, 4),
        "stream_size": (120, 8),
    }

    def __init__(self, data: bytes | mmap.mmap, *, _mmap_owner: mmap.mmap | None = None) -> None:
        self._data = data
        self._mmap_owner = _mmap_owner
        self.header = self._parse_header()
        self._validate_header()
        self.difat: List[SectorNumber] = self._build_difat()
        self.fat: List[int] = self._build_fat()
        self.mini_fat: List[int] = self._build_mini_fat()
        self.directory_entries = self._build_directory_entries()
        self.root_entry = self._get_root_entry()
        self.mini_stream = self._read_stream_bytes(self.root_entry) if self.root_entry.stream_size > 0 else b""
        self.stream_data: Dict[StreamId, bytes] = {}
        self.stream_data[self.root_entry.stream_id] = self.mini_stream

    @classmethod
    def from_file(cls, path: Path | str) -> "CFBReader":
        p = Path(path)
        with p.open("rb") as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        return cls(mm, _mmap_owner=mm)

    def close(self) -> None:
        if self._mmap_owner is not None:
            self._mmap_owner.close()
            self._mmap_owner = None

    def __enter__(self) -> "CFBReader":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    @property
    def data_size(self) -> int:
        return len(self._data)

    @property
    def major_version(self) -> int:
        return self.header.major_version

    @property
    def sector_size(self) -> int:
        return self.header.sector_size

    @property
    def mini_sector_size(self) -> int:
        return self.header.mini_sector_size

    @property
    def fat_sector_count(self) -> int:
        return self.header.number_of_fat_sectors

    @property
    def directory_entry_count(self) -> int:
        return len(self.directory_entries)

    @property
    def materialized_stream_count(self) -> int:
        return len(self.stream_data)

    @property
    def file_size(self) -> int:
        return len(self._data)

    def get_entry(self, stream_id: StreamId) -> DirectoryEntry:
        return self.directory_entries[stream_id]

    def get_stream_data(self, stream_id: StreamId) -> bytes:
        if stream_id not in self.stream_data:
            entry = self.get_entry(stream_id)
            if not (entry.is_stream() or entry.is_root()):
                raise CFBError(f"Stream data is not available for non-stream entry stream_id={stream_id}")
            self.stream_data[stream_id] = self._read_stream_bytes(entry)
        return self.stream_data[stream_id]

    def iter_storages(self) -> Iterator[DirectoryEntry]:
        for entry in self.directory_entries:
            if entry.is_storage():
                yield entry

    def iter_streams(self) -> Iterator[DirectoryEntry]:
        for entry in self.directory_entries:
            if entry.is_stream():
                yield entry

    def iter_children(self, storage_stream_id: StreamId) -> Iterator[DirectoryEntry]:
        storage = self.get_entry(storage_stream_id)
        if not storage.is_storage() or storage.child_id == NOSTREAM:
            return
        for sid in self._collect_siblings_in_order(storage.child_id):
            yield self.directory_entries[sid]

    def iter_tree(self, start_stream_id: StreamId = ROOT_STREAM_ID) -> Iterator[Tuple[int, DirectoryEntry]]:
        """Yield a depth-first tree traversal as `(depth, entry)` tuples."""
        stack: List[Tuple[int, StreamId]] = [(0, start_stream_id)]
        while stack:
            depth, sid = stack.pop()
            entry = self.directory_entries[sid]
            yield (depth, entry)
            if entry.is_storage() and entry.child_id != NOSTREAM:
                child_ids = self._collect_siblings_in_order(entry.child_id)
                for child_sid in reversed(child_ids):
                    stack.append((depth + 1, child_sid))

    def find_child_by_name(self, storage_stream_id: StreamId, name: str) -> Optional[DirectoryEntry]:
        for child in self.iter_children(storage_stream_id):
            if child.name == name:
                return child
        return None

    def resolve_path(self, names: Iterable[str], start_stream_id: StreamId = ROOT_STREAM_ID) -> Optional[DirectoryEntry]:
        """Resolve a storage/stream path by exact directory-entry names."""
        current_sid = start_stream_id
        current = self.directory_entries[current_sid]
        for part in names:
            if not current.is_storage():
                return None
            child = self.find_child_by_name(current_sid, part)
            if child is None:
                return None
            current_sid = child.stream_id
            current = child
        return current

    def _parse_header(self) -> Header:
        if len(self._data) < 512:
            raise CFBError("File is too small to contain a Compound File Binary (CFB) header.")

        signature = self._data[0:8]
        if signature != b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
            raise CFBError("Invalid Compound File Binary (CFB) signature.")

        header_signature = self._data[self.HEADER_LAYOUT["header_signature"][0] : self.HEADER_LAYOUT["header_signature"][0] + 8]
        header_clsid = self._data[self.HEADER_LAYOUT["header_clsid"][0] : self.HEADER_LAYOUT["header_clsid"][0] + 16]
        minor_version = struct.unpack_from("<H", self._data, self.HEADER_LAYOUT["minor_version"][0])[0]
        major_version = struct.unpack_from("<H", self._data, self.HEADER_LAYOUT["major_version"][0])[0]
        byte_order = struct.unpack_from("<H", self._data, self.HEADER_LAYOUT["byte_order"][0])[0]
        sector_shift = struct.unpack_from("<H", self._data, self.HEADER_LAYOUT["sector_shift"][0])[0]
        mini_sector_shift = struct.unpack_from("<H", self._data, self.HEADER_LAYOUT["mini_sector_shift"][0])[0]
        reserved = self._data[self.HEADER_LAYOUT["reserved"][0] : self.HEADER_LAYOUT["reserved"][0] + 6]
        number_of_directory_sectors = struct.unpack_from("<I", self._data, self.HEADER_LAYOUT["number_of_directory_sectors"][0])[0]
        number_of_fat_sectors = struct.unpack_from("<I", self._data, self.HEADER_LAYOUT["number_of_fat_sectors"][0])[0]
        first_directory_sector_location = SectorNumber(
            struct.unpack_from(
            "<I", self._data, self.HEADER_LAYOUT["first_directory_sector_location"][0]
        )[0]
        )
        transaction_signature_number = struct.unpack_from("<I", self._data, self.HEADER_LAYOUT["transaction_signature_number"][0])[0]
        mini_stream_cutoff_size = struct.unpack_from("<I", self._data, self.HEADER_LAYOUT["mini_stream_cutoff_size"][0])[0]
        first_mini_fat_sector_location = SectorNumber(
            struct.unpack_from(
            "<I", self._data, self.HEADER_LAYOUT["first_mini_fat_sector_location"][0]
        )[0]
        )
        number_of_mini_fat_sectors = struct.unpack_from(
            "<I", self._data, self.HEADER_LAYOUT["number_of_mini_fat_sectors"][0]
        )[0]
        first_difat_sector_location = SectorNumber(
            struct.unpack_from("<I", self._data, self.HEADER_LAYOUT["first_difat_sector_location"][0])[0]
        )
        number_of_difat_sectors = struct.unpack_from("<I", self._data, self.HEADER_LAYOUT["number_of_difat_sectors"][0])[0]
        difat = [SectorNumber(x) for x in struct.unpack_from("<109I", self._data, self.HEADER_LAYOUT["difat"][0])]

        if byte_order != BYTE_ORDER_LITTLE_ENDIAN:
            raise CFBError("Unsupported byte order; expected little-endian marker 0xFFFE.")

        return Header(
            header_signature=header_signature,
            header_clsid=header_clsid,
            minor_version=minor_version,
            major_version=major_version,
            byte_order=byte_order,
            sector_shift=sector_shift,
            mini_sector_shift=mini_sector_shift,
            reserved=reserved,
            number_of_directory_sectors=number_of_directory_sectors,
            number_of_fat_sectors=number_of_fat_sectors,
            first_directory_sector_location=first_directory_sector_location,
            transaction_signature_number=transaction_signature_number,
            mini_stream_cutoff_size=mini_stream_cutoff_size,
            first_mini_fat_sector_location=first_mini_fat_sector_location,
            number_of_mini_fat_sectors=number_of_mini_fat_sectors,
            first_difat_sector_location=first_difat_sector_location,
            number_of_difat_sectors=number_of_difat_sectors,
            difat=difat,
        )

    def _validate_header(self) -> None:
        if self.header.major_version not in (3, 4):
            raise CFBError(f"Unsupported major version: {self.header.major_version}")
        expected_shift = 9 if self.header.major_version == 3 else 12
        if self.header.sector_shift != expected_shift:
            raise CFBError(
                f"Invalid sector shift {self.header.sector_shift} for version {self.header.major_version}."
            )
        if self.header.mini_sector_shift != 6:
            raise CFBError(f"Invalid mini sector shift: {self.header.mini_sector_shift}")
        if self.header.mini_stream_cutoff_size != MINI_STREAM_CUTOFF_SIZE:
            raise CFBError(f"Invalid mini stream cutoff size: {self.header.mini_stream_cutoff_size}")
        if self.header.header_clsid != b"\x00" * 16:
            raise CFBError("Invalid header CLSID; expected all zeroes.")
        if self.header.major_version == 3 and self.header.number_of_directory_sectors != 0:
            raise CFBError("For version 3, number_of_directory_sectors must be zero.")

    def _sector_offset(self, sector_number: SectorNumber) -> int:
        if sector_number > MAXREGSECT:
            raise CFBError(f"Invalid sector number: {sector_number:#x}")
        return (sector_number + 1) * self.header.sector_size

    def _read_sector(self, sector_number: SectorNumber) -> bytes:
        offset = self._sector_offset(sector_number)
        end = offset + self.header.sector_size
        if end > len(self._data):
            raise CFBError(f"Sector {sector_number} points past end of file.")
        return self._data[offset:end]

    def _build_difat(self) -> List[SectorNumber]:
        difat_entries = [x for x in self.header.difat if x != SectorMarker.FREESECT]
        next_difat_sector = self.header.first_difat_sector_location
        visited: Set[int] = set()

        for _ in range(self.header.number_of_difat_sectors):
            if next_difat_sector in (SectorMarker.ENDOFCHAIN, SectorMarker.FREESECT):
                break
            if next_difat_sector in visited:
                raise CFBError("Cycle detected in DIFAT chain.")
            visited.add(next_difat_sector)

            sector_data = self._read_sector(next_difat_sector)
            entries_per_sector = (self.header.sector_size // 4) - 1
            entries = list(struct.unpack_from(f"<{entries_per_sector}I", sector_data, 0))
            for entry in entries:
                if entry != SectorMarker.FREESECT:
                    difat_entries.append(SectorNumber(entry))
            next_difat_sector = SectorNumber(struct.unpack_from("<I", sector_data, self.header.sector_size - 4)[0])

        return difat_entries[: self.header.number_of_fat_sectors]

    def _build_fat(self) -> List[int]:
        fat_entries: List[int] = []
        entries_per_sector = self.header.sector_size // 4
        for fat_sector in self.difat:
            sector_data = self._read_sector(fat_sector)
            fat_entries.extend(struct.unpack_from(f"<{entries_per_sector}I", sector_data, 0))
        return fat_entries

    def _iter_chain(self, start_sector: SectorNumber) -> List[SectorNumber]:
        if start_sector in (SectorMarker.ENDOFCHAIN, SectorMarker.FREESECT):
            return []

        chain: List[SectorNumber] = []
        seen: Set[int] = set()
        sector = start_sector
        while sector != SectorMarker.ENDOFCHAIN:
            if sector in seen:
                raise CFBError("Cycle detected in sector chain.")
            if sector >= len(self.fat):
                raise CFBError(f"Sector {sector} is outside FAT range.")
            seen.add(sector)
            chain.append(sector)
            nxt = self.fat[sector]
            if nxt in (SectorMarker.FATSECT, SectorMarker.DIFSECT):
                raise CFBError("Invalid chain link to FAT/DIFAT sector marker.")
            sector = SectorNumber(nxt)
        return chain

    def _build_mini_fat(self) -> List[int]:
        mini_fat: List[int] = []
        if self.header.number_of_mini_fat_sectors == 0:
            return mini_fat
        chain = self._iter_chain(self.header.first_mini_fat_sector_location)
        entries_per_sector = self.header.sector_size // 4
        for sector in chain:
            sector_data = self._read_sector(sector)
            mini_fat.extend(struct.unpack_from(f"<{entries_per_sector}I", sector_data, 0))
        return mini_fat

    def _build_directory_entries(self) -> List[DirectoryEntry]:
        chain = self._iter_chain(self.header.first_directory_sector_location)
        raw = bytearray()
        for sector in chain:
            raw.extend(self._read_sector(sector))

        entries: List[DirectoryEntry] = []
        for i in range(0, len(raw), 128):
            chunk = raw[i : i + 128]
            if len(chunk) < 128:
                break

            name_len = struct.unpack_from("<H", chunk, self.DIRECTORY_ENTRY_LAYOUT["directory_entry_name_length"][0])[0]
            object_type_raw = chunk[self.DIRECTORY_ENTRY_LAYOUT["object_type"][0]]
            try:
                object_type = DirectoryObjectType(object_type_raw)
            except ValueError as exc:
                raise CFBError(f"Invalid directory entry object_type value: {object_type_raw}") from exc
            color_raw = chunk[self.DIRECTORY_ENTRY_LAYOUT["color_flag"][0]]
            try:
                color_flag = DirectoryColorFlag(color_raw)
            except ValueError as exc:
                raise CFBError(f"Invalid directory entry color_flag value: {color_raw}") from exc
            left_sibling_id = struct.unpack_from("<I", chunk, self.DIRECTORY_ENTRY_LAYOUT["left_sibling_id"][0])[0]
            right_sibling_id = struct.unpack_from("<I", chunk, self.DIRECTORY_ENTRY_LAYOUT["right_sibling_id"][0])[0]
            child_id = struct.unpack_from("<I", chunk, self.DIRECTORY_ENTRY_LAYOUT["child_id"][0])[0]
            clsid = bytes(chunk[self.DIRECTORY_ENTRY_LAYOUT["clsid"][0] : self.DIRECTORY_ENTRY_LAYOUT["clsid"][0] + 16])
            state_bits = struct.unpack_from("<I", chunk, self.DIRECTORY_ENTRY_LAYOUT["state_bits"][0])[0]
            creation_time = FileTime(struct.unpack_from("<Q", chunk, self.DIRECTORY_ENTRY_LAYOUT["creation_time"][0])[0])
            modified_time = FileTime(struct.unpack_from("<Q", chunk, self.DIRECTORY_ENTRY_LAYOUT["modified_time"][0])[0])
            starting_sector_location = struct.unpack_from(
                "<I", chunk, self.DIRECTORY_ENTRY_LAYOUT["starting_sector_location"][0]
            )[0]
            stream_size = struct.unpack_from("<Q", chunk, self.DIRECTORY_ENTRY_LAYOUT["stream_size"][0])[0]

            # In v3, upper 32 bits may be uninitialized. [MS-CFB] recommends ignoring them.
            if self.header.major_version == 3:
                stream_size &= 0xFFFFFFFF

            if name_len >= 2:
                name_raw = bytes(chunk[0 : max(0, name_len - 2)])
                name = name_raw.decode("utf-16le", errors="replace")
            else:
                name = ""

            entries.append(
                DirectoryEntry(
                    stream_id=StreamId(len(entries)),
                    name=name,
                    directory_entry_name_length=name_len,
                    object_type=object_type,
                    color_flag=color_flag,
                    left_sibling_id=StreamId(left_sibling_id),
                    right_sibling_id=StreamId(right_sibling_id),
                    child_id=StreamId(child_id),
                    clsid=clsid,
                    state_bits=state_bits,
                    creation_time=creation_time,
                    modified_time=modified_time,
                    starting_sector_location=SectorNumber(starting_sector_location),
                    stream_size=stream_size,
                )
            )
        return entries

    def _get_root_entry(self) -> DirectoryEntry:
        if not self.directory_entries:
            raise CFBError("No directory entries found.")
        root = self.directory_entries[0]
        if not root.is_root():
            raise CFBError("Directory entry 0 is not root storage.")
        if root.stream_id != ROOT_STREAM_ID:
            raise CFBError("Invalid root stream id.")
        return root

    def _read_stream_bytes(self, entry: DirectoryEntry) -> bytes:
        if entry.stream_size == 0:
            return b""

        if entry.is_root() or entry.stream_size < self.header.mini_stream_cutoff_size:
            if entry.is_root():
                chain = self._iter_chain(entry.starting_sector_location)
                out = bytearray()
                for sector in chain:
                    out.extend(self._read_sector(sector))
                return bytes(out[: entry.stream_size])

            if not self.mini_stream:
                return b""
            out = bytearray()
            seen: Set[int] = set()
            mini_sector = entry.starting_sector_location
            while mini_sector != SectorMarker.ENDOFCHAIN:
                if mini_sector in seen:
                    raise CFBError("Cycle detected in mini FAT chain.")
                if mini_sector >= len(self.mini_fat):
                    raise CFBError(f"Mini sector {mini_sector} is outside mini FAT range.")
                seen.add(mini_sector)
                offset = mini_sector * self.header.mini_sector_size
                end = offset + self.header.mini_sector_size
                if end > len(self.mini_stream):
                    raise CFBError("Mini sector points past mini-stream length.")
                out.extend(self.mini_stream[offset:end])
                mini_sector = SectorNumber(self.mini_fat[mini_sector])
            return bytes(out[: entry.stream_size])

        chain = self._iter_chain(entry.starting_sector_location)
        out = bytearray()
        for sector in chain:
            out.extend(self._read_sector(sector))
        return bytes(out[: entry.stream_size])

    def _read_all_streams(self) -> None:
        for entry in self.directory_entries:
            if entry.is_stream() or entry.is_root():
                self.stream_data[entry.stream_id] = self._read_stream_bytes(entry)

    def _collect_siblings_in_order(self, start_id: StreamId) -> List[StreamId]:
        result: List[StreamId] = []
        stack: List[StreamId] = []
        active: Set[int] = set()
        emitted: Set[int] = set()
        current = start_id

        while current != NOSTREAM or stack:
            while current != NOSTREAM:
                if current >= len(self.directory_entries):
                    raise CFBError(f"Invalid stream id in sibling tree: {current}")
                if current in active:
                    raise CFBError("Cycle detected in directory sibling tree.")
                active.add(current)
                stack.append(current)
                current = self.directory_entries[current].left_sibling_id

            node_id = stack.pop()
            active.remove(node_id)
            if node_id in emitted:
                raise CFBError("Duplicate node encountered in directory sibling tree.")
            emitted.add(node_id)
            result.append(node_id)
            current = self.directory_entries[node_id].right_sibling_id

        return result
