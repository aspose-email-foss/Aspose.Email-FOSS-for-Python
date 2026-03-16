# Contributing

## Development Setup

Use Python 3.10 or newer.

Install the package in editable mode:

```bash
pip install -e .
```

Run publishable tests:

```bash
python -m unittest discover -s tests -v
```

## Packaging Checks

Build source and wheel distributions:

```bash
python -m build
```

Validate package metadata:

```bash
python -m twine check dist/*
```

## Release Checklist

1. Update [CHANGELOG.md](CHANGELOG.md).
2. Verify [README.md](README.md), [examples/](examples), and package metadata in [pyproject.toml](pyproject.toml).
3. Run tests.
4. Build distributions.
5. Run `twine check`.
6. Upload to PyPI when the package name and publisher account are ready.
