# Aspose.Email FOSS for Python

## Repository Goal

This repository provides a pure Python package for working with:

- Outlook MSG files
- Compound File Binary (CFB) containers
- High-level MAPI-style message objects
- Conversion to and from Python's [`email.message.EmailMessage`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage)

Package name:
- `aspose-email-foss`

Public Python import root:
- `aspose.email_foss`

Primary public modules:
- `aspose.email_foss.msg`
- `aspose.email_foss.cfb`

## Repository Layout

- `aspose/email_foss/msg/`: MSG reader, writer, and high-level message API
- `aspose/email_foss/cfb/`: CFB reader and writer
- `examples/`: end-user examples
- `tests/`: self-contained test suite
- [`README.md`](README.md): package overview and usage
- [`CHANGELOG.md`](CHANGELOG.md): release notes
- [`CITATION.cff`](CITATION.cff): citation metadata for the repository
- [`pyproject.toml`](pyproject.toml): package metadata

## Public API Rules

Prefer these imports in documentation and examples:

```python
from aspose.email_foss import msg
from aspose.email_foss import cfb
```

Direct submodule imports are also acceptable when they make examples clearer:

```python
from aspose.email_foss.msg import MapiMessage
from aspose.email_foss.cfb import CFBReader
```

Do not introduce undocumented import roots.

## Code Organization Rules

Keep runtime code under:
- `aspose/email_foss/msg/`
- `aspose/email_foss/cfb/`

Keep examples under:
- `examples/`

Keep tests under:
- `tests/`

Do not add debug dumps, local scratch scripts, generated caches, or experimental helpers to the repository root.

## Testing Rules

Run the main test suite with:

```bash
python -m unittest discover -s tests -v
```

Tests should:
- be deterministic
- be self-contained
- avoid network access
- avoid machine-specific assumptions
- use only repository-local code and in-memory sample data when practical

## Documentation Rules

README should clearly show:
- installation
- supported import patterns
- common tasks
- short copy-pasteable examples
- links to official documentation when referencing Python stdlib APIs

Examples should:
- use the public package namespace
- focus on realistic user workflows
- stay short and runnable

## Packaging Rules

Package metadata lives in:
- [`pyproject.toml`](pyproject.toml)

Versioning scheme:
- `YY.M`
- example: `26.3`

Before release, keep these files aligned:
- [`pyproject.toml`](pyproject.toml)
- [`README.md`](README.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`CITATION.cff`](CITATION.cff)

## Changelog Rules

Maintain [`CHANGELOG.md`](CHANGELOG.md) using the principles of [Keep a Changelog](https://keepachangelog.com/).

Rules:
- Every user-visible change must be recorded in [`CHANGELOG.md`](CHANGELOG.md).
- Write entries for humans, not as raw commit summaries.
- Group entries under standard Keep a Changelog sections when applicable:
  - `Added`
  - `Changed`
  - `Deprecated`
  - `Removed`
  - `Fixed`
  - `Security`
- Do not create empty sections.
- Use one version heading per release in this format:
  - `## [YY.M] - YYYY-MM-DD`
- The first released version should describe the first public release explicitly when applicable.
- Keep entries concise and user-facing.
- Do not list purely internal refactors unless they affect users, packaging, examples, tests users run, or documented behavior.
- If public API changes, mention the affected import path, class, method, or behavior explicitly.
- If compatibility changes, mention the external format or workflow affected, such as MSG writing, Outlook interoperability, or `EmailMessage` conversion.

When preparing a release:
- update the version in [`pyproject.toml`](pyproject.toml)
- add or finalize the matching version section in [`CHANGELOG.md`](CHANGELOG.md)
- ensure [`README.md`](README.md) examples and wording match the released behavior

## API Change Rules

When changing runtime behavior:
- update tests
- update examples if public usage changes
- update README if the public API changes

When adding new API:
- prefer explicit and discoverable interfaces
- preserve backward compatibility when practical
- document the new entry point in README

## Compatibility Guidance

Prioritize:
- correct MSG read/write behavior
- stable CFB container behavior
- practical interoperability with Outlook-generated content
- reliable conversion to and from `EmailMessage`

Be explicit about limitations rather than hiding them.

## Preferred Repository Additions

Useful companion files for AI agents and contributors:
- [`PUBLIC_API.md`](PUBLIC_API.md): stable classes, functions, and imports
- [`examples/README.md`](examples/README.md): task-to-example index
- [`llms.txt`](llms.txt): short machine-oriented repository map

## Non-Goals

This repository should not turn into:
- a generic mail server library
- an Outlook automation wrapper
- a collection of ad hoc debug utilities
- a dumping ground for one-off scripts
