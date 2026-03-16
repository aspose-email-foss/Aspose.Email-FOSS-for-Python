from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from aspose.email_foss import msg


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump summary for Outlook .msg using MapiMessage.")
    parser.add_argument("msg_path", type=Path, help="Path to a .msg file")
    parser.add_argument(
        "--body-preview-chars",
        type=int,
        default=400,
        help="Max number of body characters to print (default: 400).",
    )
    parser.add_argument(
        "--property-id",
        type=str,
        default=None,
        help="Optional property id to read (hex like 0x0037 or decimal).",
    )
    parser.add_argument(
        "--property-type",
        type=str,
        default=None,
        help="Optional property type to read (hex like 0x001F or decimal).",
    )
    parser.add_argument(
        "--property-storage-sid",
        type=int,
        default=0,
        help="Storage stream id for property lookup (default: 0 for top-level).",
    )
    parser.add_argument(
        "--property-raw",
        action="store_true",
        help="Return raw bytes for property lookup instead of decoded value.",
    )
    args = parser.parse_args()

    with msg.MapiMessage.from_file(args.msg_path) as message:
        email_message = message.to_email_message()
        attachments = list(message.iter_attachments_info())

        print("Message Projection:")
        print(f"file: {args.msg_path}")
        print(f"content_type: {email_message.get_content_type()}")
        print(f"is_multipart: {email_message.is_multipart()}")
        print(f"headers_count: {len(email_message)}")
        print(f"attachments_count: {len(attachments)}")

        print("\nHeaders:")
        for key, value in email_message.items():
            print(f"- {key}: {value}")

        print("\nBody Preview:")
        body_part = email_message.get_body(preferencelist=("plain", "html"))
        body = body_part.get_content() if body_part is not None else email_message.get_content()
        body_preview = body[: args.body_preview_chars]
        print(body_preview)
        if len(body) > len(body_preview):
            print(f"... ({len(body) - len(body_preview)} more chars omitted)")

        print("\nAttachments:")
        if not attachments:
            print("- <none>")
        else:
            for idx, att in enumerate(attachments, start=1):
                print(
                    f"- [{idx}] name={att.filename} mime={att.mime_type} size={len(att.data)} "
                    f"content_id={att.content_id or ''} storage={att.storage_name or ''}"
                )

        print("\nAttachment Memory Read Check:")
        mime_attachments = list(email_message.iter_attachments())
        if not mime_attachments:
            print("- <none>")
        else:
            for idx, part in enumerate(mime_attachments, start=1):
                filename = part.get_filename() or f"attachment-{idx}"
                payload = part.get_content()
                if isinstance(payload, str):
                    payload_bytes = payload.encode("utf-8", errors="replace")
                else:
                    payload_bytes = bytes(payload)
                print(
                    f"- [{idx}] name={filename} read_ok=True bytes_in_memory={len(payload_bytes)} "
                    f"content_type={part.get_content_type()}"
                )

        if args.property_id is not None:
            prop_id = int(args.property_id, 0)
            prop_type = int(args.property_type, 0) if args.property_type is not None else None
            value = message.get_property_value(
                prop_id,
                prop_type,
                storage_stream_id=args.property_storage_sid,
                decode=not args.property_raw,
            )
            print("\nArbitrary Property Lookup:")
            print(f"- property_id=0x{prop_id:04X}")
            print(f"- property_type={f'0x{prop_type:04X}' if prop_type is not None else '<auto>'}")
            print(f"- storage_sid={args.property_storage_sid}")
            if value is None:
                print("- value=<not found>")
            elif isinstance(value, (bytes, bytearray)):
                print(f"- value_type=bytes")
                print(f"- value_len={len(value)}")
                print(f"- value_hex={value.hex()[:256]}{'...' if len(value) > 128 else ''}")
            else:
                print(f"- value_type={type(value).__name__}")
                print(f"- value={value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
