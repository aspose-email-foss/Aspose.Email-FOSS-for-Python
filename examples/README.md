# Examples

This file maps common tasks to example scripts.

## Quick Index

- Create a new `.msg`, read it back, convert to `.eml`:
  - [create_msg_and_eml.py](create_msg_and_eml.py)
- Read low-level MSG and CFB structure:
  - [msg_reader.py](msg_reader.py)
- Read a message through the high-level API and print a summary:
  - [msg_summary.py](msg_summary.py)

## Example Scripts

### [create_msg_and_eml.py](create_msg_and_eml.py)

Use this example to:
- create a new `MapiMessage`
- set common properties through `PropertyId`
- add recipients
- add attachments
- save as `.msg`
- load the `.msg` back
- convert the loaded message to [`email.message.EmailMessage`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage)
- save the converted message as `.eml`

Run:

```bash
python examples/create_msg_and_eml.py
```

Optional output paths:

```bash
python examples/create_msg_and_eml.py --msg-path example-message.msg --eml-path example-message.eml
```

### [msg_reader.py](msg_reader.py)

Use this example to:
- open a `.msg` through `MsgReader`
- inspect CFB geometry
- inspect property stream headers
- list recipient and attachment storages
- dump the CFB tree

Run:

```bash
python examples/msg_reader.py <path-to-msg>
```

### [msg_summary.py](msg_summary.py)

Use this example to:
- open a `.msg` through `MapiMessage`
- project it to [`email.message.EmailMessage`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage)
- print headers
- print body preview
- list attachments
- inspect an arbitrary MAPI property

Run:

```bash
python examples/msg_summary.py <path-to-msg>
```

## Recommended Starting Points

- If you want a complete end-to-end workflow, start with [create_msg_and_eml.py](create_msg_and_eml.py).
- If you want to inspect container internals, start with [msg_reader.py](msg_reader.py).
- If you want a high-level projection of an existing message, start with [msg_summary.py](msg_summary.py).
