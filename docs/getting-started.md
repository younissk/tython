# Getting Started

Start here if you want the shortest path into Tython.

## Read Order

1. [Installation](installation.md)
2. [Quickstart](language/quickstart.md)
3. [Values and Bindings](language/values-and-bindings.md)
4. [Expressions](language/expressions.md)
5. [Functions](language/functions.md)

## Repo Shape

- `parser/` holds parser, lowering, semantics, CLI, and LSP code.
- `grammar/` holds grammar sources.
- `tests/` holds smoke, golden, lowering, and differential coverage.
- `docs/` holds the MkDocs site.

## Docs Principle

Docs track compiler behavior.
If syntax, typing, diagnostics, or tooling changes, update the docs in same change.

