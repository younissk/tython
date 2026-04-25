# Debugging Guide

Use the smallest failing case first.

## Triage Order

1. `tython format <file>`
2. `tython lint <file>`
3. `uv run python -m pytest -m smoke`
4. `uv run python -m pytest -m lowering`
5. `uv run python -m pytest -m differential`

## If Parse Fails

- Check syntax against `docs/language/*.md`.
- Check the diagnostic code in `docs/reference/error-codes.md`.
- Reduce to one function, one block, one expression.

## If Semantics Fail

- Confirm declaration order.
- Confirm names follow casing rules.
- Confirm return types and throws clauses match use sites.

## If LSP Seems Wrong

- Restart server.
- Check `TYTHON_LSP_LOG`.
- Reproduce with `tython lsp start` in terminal before editor debugging.

