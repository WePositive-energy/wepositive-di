# Development

This project uses Poetry, Ruff, Pyright, Pytest, and MkDocs.

## Setup

```bash
poetry install --with dev,docs
poetry run pre-commit install
```

The `dev` group contains test, linting, type-checking, and pre-commit tools.
The `docs` group contains MkDocs and mkdocstrings dependencies used to build the
documentation locally.

## Tests and checks

```bash
poetry run pytest
poetry run ruff check
poetry run pyright
poetry run pre-commit run --all-files
```

Coverage is configured in `pyproject.toml` and currently requires 100% coverage
for `src/wepositive_di`.

## Documentation

Build the docs with:

```bash
poetry run mkdocs build
```

Serve them locally with:

```bash
poetry run mkdocs serve
```

The documentation source lives in `docs/`; `mkdocs.yml` controls navigation,
theme settings, and mkdocstrings API reference generation.

## Versioning

Before release changes are pushed, bump the package version:

```bash
poetry version prerelease
```
