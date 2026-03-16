# Aspose.Email FOSS for Python

Aspose.Email FOSS for Python is a pure Python toolkit for working with:

- Compound File Binary (CFB) containers
- Outlook MSG files
- High-level MAPI-style message objects
- [`email.message.EmailMessage`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage) conversion

It is focused on practical MSG read/write workflows in a lightweight open-source package.

## Features

- Read CFB and Outlook MSG containers
- Inspect low-level storages, streams, and property bags
- Read, edit, and write messages through `MapiMessage`
- Work with recipients, attachments, and embedded messages
- Convert between MSG and [`email.message.EmailMessage`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage)
- Create new Outlook-compatible `.msg` files in pure Python

## Installation

```bash
pip install aspose-email-foss
```

## Quick Start

```python
from datetime import datetime, timezone

from aspose.email_foss import msg

message = msg.MapiMessage.create("Hello", "Body")
message.set_property(msg.PropertyId.SENDER_NAME, "Build Agent")
message.set_property(msg.PropertyId.SENDER_EMAIL_ADDRESS, "build.agent@example.com")
message.set_property(msg.PropertyId.MESSAGE_DELIVERY_TIME, datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc))
message.add_recipient("alice@example.com", display_name="Alice Example")
message.add_attachment("hello.txt", b"sample attachment\n", mime_type="text/plain")
message.save("example-message.msg")

with msg.MapiMessage.from_file("example-message.msg") as loaded:
    email_message = loaded.to_email_message()
    print(email_message["Subject"])
```

## Package Entry Points

- `aspose.email_foss.msg.MapiMessage`: high-level mutable MSG model
- `aspose.email_foss.msg.MsgReader`: low-level MSG reader
- `aspose.email_foss.msg.MsgWriter`: low-level MSG writer
- `aspose.email_foss.cfb.CFBReader`: low-level CFB reader
- `aspose.email_foss.cfb.CFBWriter`: low-level CFB writer

## Compatibility

Main supported scenarios:

- Read Outlook `.msg` files
- Write Outlook `.msg` files
- Inspect Compound File Binary (CFB) containers
- Convert `.msg` to `.eml`
- Convert `.eml` to `.msg`
- Work with recipients, attachments, and embedded messages

API layers:

- High-level MSG API: `aspose.email_foss.msg`, centered around `MapiMessage`
- Low-level MSG API: `aspose.email_foss.msg`, centered around `MsgReader`, `MsgWriter`, and `MsgDocument`
- Low-level CFB API: `aspose.email_foss.cfb`, centered around `CFBReader`, `CFBWriter`, and `CFBDocument`

[`email.message.EmailMessage`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage) interop:

- `MapiMessage.from_email_message(...)`
- `MapiMessage.to_email_message()`

Outlook-oriented behavior:

- standard message creation
- recipients
- file attachments
- embedded message attachments
- common message property defaults for practical Outlook interoperability

For the stable API summary, see [PUBLIC_API.md](PUBLIC_API.md).
For runnable scenarios, see [examples](examples).

## Examples

### Convert MSG to EML

```python
from aspose.email_foss import msg

with msg.MapiMessage.from_file("message.msg") as message:
    email_message = message.to_email_message()

with open("message.eml", "wb") as target:
    target.write(email_message.as_bytes())
```

### Convert EML to MSG

```python
from email import policy
from email.parser import BytesParser

from aspose.email_foss import msg

with open("message.eml", "rb") as source:
    email_message = BytesParser(policy=policy.default).parse(source)

message = msg.MapiMessage.from_email_message(email_message)
message.save("message.msg")
```

## Links

- Repository: <https://github.com/aspose-email-foss/Aspose.Email-FOSS-for-Python>
- Issues: <https://github.com/aspose-email-foss/Aspose.Email-FOSS-for-Python/issues>
- PyPI: <https://pypi.org/project/aspose-email-foss/>

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
