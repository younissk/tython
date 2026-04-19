# AGENTS Guide

This repository is organized around grammar experimentation and parser validation.

## Directories

- `grammar/`: grammar sources (`python.gram`, `Tokens`)
- `parser/`: parser package
- `parser/core.py`: parser-facing API (`parse`, `parse_custom`, `lower`)
- `parser/lowering.py`: lowering transforms from custom IR to Python AST
- `tests/`: parser test framework
- `tests/cases/`: file-based test fixtures grouped by test layer

## Working Rules

- Keep grammar edits in `grammar/` only.
- Keep parser-facing API stable in `parser/core.py` (`parse`, `parse_custom`, `lower`).
- Add tests for each grammar change in at least the smoke and differential layers.

## Test Strategy (Four Layers)

1. `smoke`: parse success/failure checks only.
2. `golden`: AST snapshot checks to catch grammar drift.
3. `lowering`: custom-IR-to-Python-AST expectations.
4. `differential`: compare output with CPython `ast.parse` + compile checks.

## How to Test Regression Over Time

Create a `tests/cases/` folder with files.

Example:

```text
tests/cases/valid/
  simple_import.dp
  simple_assign.dp
  enum_basic.dp

tests/cases/invalid/
  broken_import.dp
  broken_enum.dp
```

Then write a test runner that walks those folders:

- everything in `valid/` must parse
- everything in `invalid/` must fail
- optionally compare produced output to `expected/*.py`

This becomes your regression suite. Every time you change the grammar, run it.

Even better, add two special folders:

- `compat_python/`: files that should behave exactly like Python
- `custom_syntax/`: files that use your extensions

That separation is important. It shows whether you broke Python compatibility or only broke custom features.

## Commands

- Run full suite: `uv run python -m pytest`
- Run one layer: `uv run python -m pytest -m smoke`
- Run one file: `uv run python -m pytest tests/test_differential.py`

## User Collaboration Preferences

Use these preferences as default behavior in future chats for this repository:

- Execute requests end-to-end by default (do not stop at planning unless explicitly asked).
- Keep parser public APIs stable: `parse`, `parse_custom`, `lower`.
- Prefer strict, predictable language rules over permissive behavior.
- Favor Python-compatible syntax/semantics only when they remain boring and explicit.
- Preserve static typing strictness (no implicit coercions, clear type errors).
- Prioritize clear, actionable compile-time errors with consistent error codes and hints.
- Keep docs user-facing as language documentation (not internal/v1 planning notes).
- When adding features, include comprehensive fixtures and tests across smoke/golden/lowering/differential.
- Maintain `make` shortcuts for practical workflows (for example `make repl`).
- Keep naming/scope/mutability rules strict and explicit.
