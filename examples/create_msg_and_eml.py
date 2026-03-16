from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from aspose.email_foss import msg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a sample MSG file, load it back, convert it to EmailMessage, and save it as EML."
    )
    parser.add_argument(
        "--msg-path",
        type=Path,
        default=Path("example-message.msg"),
        help="Output path for the generated MSG file.",
    )
    parser.add_argument(
        "--eml-path",
        type=Path,
        default=Path("example-message.eml"),
        help="Output path for the generated EML file.",
    )
    args = parser.parse_args()

    message = msg.MapiMessage.create(
        "Quarterly status update and rollout plan",
        "Hello team,\n\nPlease find the latest rollout summary attached.\n\nRegards,\nEngineering",
    )

    message.set_property(
        msg.PropertyId.SENDER_NAME,
        "Build Agent",
    )
    message.set_property(
        msg.PropertyId.SENDER_EMAIL_ADDRESS,
        "build.agent@example.com",
    )
    message.set_property(
        msg.PropertyId.INTERNET_MESSAGE_ID,
        "<example-message-001@example.com>",
    )
    message.set_property(
        msg.PropertyId.MESSAGE_DELIVERY_TIME,
        datetime(2026, 3, 15, 10, 30, tzinfo=UTC),
    )
    message.set_property(
        msg.PropertyId.DISPLAY_TO,
        "Alice Example; Bob Example",
    )
    message.set_property(
        msg.PropertyId.DISPLAY_CC,
        "Carol Example",
    )
    message.set_property(
        msg.PropertyId.DISPLAY_BCC,
        "Ops Archive",
    )
    message.set_property(
        msg.PropertyId.TRANSPORT_MESSAGE_HEADERS,
        "X-Environment: example\nX-Workflow: create-msg-and-eml\n",
    )

    message.add_recipient("alice@example.com", display_name="Alice Example")
    message.add_recipient("bob@example.com", display_name="Bob Example")
    message.add_recipient("carol@example.com", display_name="Carol Example", recipient_type=msg.RECIPIENT_TYPE_CC)
    message.add_recipient("archive@example.com", display_name="Ops Archive", recipient_type=msg.RECIPIENT_TYPE_BCC)

    message.add_attachment("hello.txt", b"sample attachment\n", mime_type="text/plain")
    message.add_attachment("report.bin", b"\x00\x01\x02\x03\x04\x05", mime_type="application/octet-stream")
    message.save(args.msg_path)

    with msg.MapiMessage.from_file(args.msg_path) as loaded_message:
        email_message = loaded_message.to_email_message()
        args.eml_path.write_bytes(email_message.as_bytes())

    print(f"MSG saved to: {args.msg_path}")
    print(f"EML saved to: {args.eml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
