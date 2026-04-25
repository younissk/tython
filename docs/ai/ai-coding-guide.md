# AI Coding Guide

This language is intentionally boring and opinionated.

## Rules

- Prefer explicit types.
- Do not invent syntax.
- Run the formatter before suggesting code.
- Keep error codes stable in docs and tests.
- Read the parser and semantics before changing syntax.

## Common Commands

```bash
tython format src/
tython lint src/
tython run src/main.ty
```

## Common Mistakes

| Mistake | Correct form |
| --- | --- |
| Python-style imports | Use Tython import syntax |
| Implicit nulls | Use explicit `none` and nullable rules |
| Guessing types | Follow declared types and error codes |

## Response Style

- Show exact file paths.
- Show exact error codes.
- Prefer small patches over broad rewrites.

