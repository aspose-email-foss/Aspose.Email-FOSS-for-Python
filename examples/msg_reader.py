from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, TypeVar

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from aspose.email_foss import msg


def _format_property_tag(property_tag: int) -> str:
    prop_type = property_tag & 0xFFFF
    prop_id = (property_tag >> 16) & 0xFFFF
    return f"0x{property_tag:08X} (id=0x{prop_id:04X}, type=0x{prop_type:04X})"


T = TypeVar("T")


def _iter_limited(items: Iterable[T], limit: int) -> tuple[list[T], int]:
    collected: list[T] = []
    total = 0
    for item in items:
        total += 1
        if len(collected) < limit:
            collected.append(item)
    return collected, total


def build_dump(reader: msg.MsgReader, msg_path: Path, max_entries: int) -> str:
    cfb = reader.cfb_reader
    lines: list[str] = []

    lines.append(f"MSG file: {msg_path}")
    lines.append("Compound File Binary (CFB) Summary:")
    lines.append(f"- major_version={cfb.major_version}")
    lines.append(f"- sector_size={cfb.sector_size}")
    lines.append(f"- mini_sector_size={cfb.mini_sector_size}")
    lines.append(f"- fat_sectors={cfb.fat_sector_count}")
    lines.append(f"- directory_entries={cfb.directory_entry_count}")
    lines.append(f"- streams_materialized={cfb.materialized_stream_count}")
    lines.append(f"- file_size={cfb.file_size}")

    header = reader.top_level_header
    lines.append("Top-level Property Header:")
    lines.append(f"- reserved_0={header.reserved_0.hex()}")
    lines.append(f"- next_recipient_id={header.next_recipient_id}")
    lines.append(f"- next_attachment_id={header.next_attachment_id}")
    lines.append(f"- recipient_count={header.recipient_count}")
    lines.append(f"- attachment_count={header.attachment_count}")
    lines.append(f"- reserved_1={header.reserved_1.hex()}")

    recipients = list(reader.iter_recipient_storages())
    attachments = list(reader.iter_attachment_storages())
    lines.append("Top-level Storages:")
    lines.append(f"- named_property_mapping={reader.storage_layout.named_property_mapping_storage.name}")
    lines.append(f"- recipients={len(recipients)}")
    lines.append(f"- attachments={len(attachments)}")

    top_props, top_total = _iter_limited(reader.iter_top_level_fixed_length_properties(), max_entries)
    lines.append(f"Top-level Fixed Property Entries: shown={len(top_props)} total={top_total}")
    for idx, entry in enumerate(top_props, start=1):
        lines.append(
            f"- [{idx}] tag={_format_property_tag(entry.property_tag)} flags=0x{entry.flags:08X} value={entry.value.hex()}"
        )
    if top_total > len(top_props):
        lines.append(f"- ... {top_total - len(top_props)} more entries omitted")

    lines.append("Recipient Storages:")
    for entry in recipients:
        _, sub_entries = reader.parse_subobject_property_stream(entry.stream_id)
        lines.append(
            f"- {entry.name} [sid={entry.stream_id}] property_entries={len(sub_entries)} stream_size={entry.stream_size}"
        )

    lines.append("Attachment Storages:")
    for entry in attachments:
        _, sub_entries = reader.parse_subobject_property_stream(entry.stream_id)
        embedded = cfb.find_child_by_name(entry.stream_id, "__substg1.0_3701000D")
        has_embedded = embedded is not None and embedded.is_storage()
        lines.append(
            f"- {entry.name} [sid={entry.stream_id}] property_entries={len(sub_entries)} embedded_message={has_embedded}"
        )

    lines.append("Compound File Binary (CFB) Tree:")
    for depth, entry in cfb.iter_tree():
        indent = "  " * depth
        if entry.is_stream() or entry.is_root():
            lines.append(
                f"{indent}- {entry.name} [sid={entry.stream_id}, type={entry.object_type}, size={entry.stream_size}]"
            )
        else:
            lines.append(f"{indent}- {entry.name} [sid={entry.stream_id}, type={entry.object_type}]")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read Outlook .msg file and dump parsed MSG and Compound File Binary (CFB) structure."
    )
    parser.add_argument("msg_path", type=Path, help="Path to a .msg file")
    parser.add_argument(
        "--max-property-entries",
        type=int,
        default=200,
        help="Maximum number of top-level fixed property entries to print (default: 200).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output text file path for the dump.",
    )
    args = parser.parse_args()

    with msg.MsgReader.from_file(args.msg_path) as reader:
        dump = build_dump(reader, args.msg_path, args.max_property_entries)

    if args.out is not None:
        args.out.write_text(dump, encoding="utf-8", newline="\n")
    else:
        print(dump)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
