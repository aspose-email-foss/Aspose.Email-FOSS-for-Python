# Public API

This document summarizes the public Python API of `aspose-email-foss`.

Package name:
- `aspose-email-foss`

Public import root:
- `aspose.email_foss`

## Preferred Imports

Use one of these styles:

```python
from aspose.email_foss import msg
from aspose.email_foss import cfb
```

or:

```python
from aspose.email_foss.msg import MapiMessage
from aspose.email_foss.cfb import CFBReader
```

## High-Level MSG API

Module:
- `aspose.email_foss.msg`

Main class:
- `MapiMessage`

Primary workflows:
- create a new message
- read an existing `.msg`
- edit properties, recipients, and attachments
- save as `.msg`
- convert to and from Python's [`email.message.EmailMessage`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage)

Common entry points:
- `MapiMessage.create(...)`
- `MapiMessage.from_file(...)`
- `MapiMessage.from_email_message(...)`
- `MapiMessage.save(...)`
- `MapiMessage.to_bytes()`
- `MapiMessage.to_email_message()`
- `MapiMessage.set_property(...)`
- `MapiMessage.get_property(...)`
- `MapiMessage.get_property_value(...)`
- `MapiMessage.add_recipient(...)`
- `MapiMessage.add_attachment(...)`
- `MapiMessage.add_embedded_message_attachment(...)`

Related public classes:
- `MapiRecipient`
- `MapiAttachment`
- `MapiProperty`
- `MapiNamedProperty`

Common property helpers:
- `PropertyId`
- `CommonMessagePropertyId`
- `PropertyTypeCode`

Common constants:
- `RECIPIENT_TYPE_TO`
- `RECIPIENT_TYPE_CC`
- `RECIPIENT_TYPE_BCC`
- `ATTACH_METHOD_BY_VALUE`
- `ATTACH_METHOD_EMBEDDED`
- `ATTACH_METHOD_STORAGE`

## Low-Level MSG API

Module:
- `aspose.email_foss.msg`

Primary classes:
- `MsgReader`
- `MsgWriter`
- `MsgDocument`
- `MsgStorage`
- `MsgStream`

Use this layer when you need:
- low-level MSG storage inspection
- direct property stream access
- structured MSG container read/write

Related public types:
- `StorageLayout`
- `PropertyStreamHeaderTopLevel`
- `PropertyStreamHeaderSubobject`
- `PropertyEntryFixedLength`

## Low-Level CFB API

Module:
- `aspose.email_foss.cfb`

Primary classes:
- `CFBReader`
- `CFBWriter`
- `CFBDocument`
- `CFBStorage`
- `CFBStream`

Use this layer when you need:
- direct Compound File Binary container access
- storage and stream traversal
- custom CFB document construction

Related public types:
- `CFBError`
- `DirectoryEntry`
- `Header`
- `DirectoryObjectType`
- `DirectoryColorFlag`
- `SectorMarker`
- `SectorNumber`
- `StreamId`
- `FileTime`

Useful constants:
- `ROOT_ENTRY_NAME`
- `ROOT_STREAM_ID`
- `MINI_STREAM_CUTOFF_SIZE`
- `NOSTREAM`
- `DIFSECT`
- `FATSECT`
- `ENDOFCHAIN`
- `FREESECT`

## Supported Workflows

The public API is intended to support:
- read `.msg`
- write `.msg`
- inspect CFB container structure
- inspect MSG property structure
- create new messages programmatically
- convert `.msg` to `.eml`
- convert `.eml` to `.msg`
- work with recipients, attachments, and embedded messages

## Stability Notes

Public API means symbols exported through:
- `aspose.email_foss.msg`
- `aspose.email_foss.cfb`

Prefer documented imports and documented classes over importing internal modules directly.

If behavior changes in a user-visible way, it should be reflected in:
- [README.md](README.md)
- [CHANGELOG.md](CHANGELOG.md)
