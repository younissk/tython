# Installation

Tython uses `uv` for local development.

## Local Setup

```bash
uv sync
```

## Docs Preview

Material for MkDocs is the docs runtime.

```bash
uv run mkdocs serve
```

Build strict static output:

```bash
uv run mkdocs build --strict
```

## CLI Preview

```bash
uv run tython --help
uv run tython lsp start
```

