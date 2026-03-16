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
3. Ensure the version in [pyproject.toml](pyproject.toml) matches the intended release.
4. Push the release changes to `master` and confirm the `CI` workflow is green.
5. Optionally run local checks: `python -m unittest discover -s tests -v`, `python -m build`, and `python -m twine check --strict dist/*`.
6. Create and push a release tag in the `vYY.M` format, for example `git tag v26.3` and `git push origin v26.3`.
7. Monitor the `Release` GitHub Actions workflow and confirm the `Publish to PyPI` job succeeds.
8. Verify the published package on PyPI and perform a smoke-install if needed.
