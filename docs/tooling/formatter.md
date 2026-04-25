# Formatter

`tython format` rewrites Tython source with repo formatting rules.

## Default Scope

Without paths, formatter walks `src/` in current project.

```bash
tython format
```

## Targeted Format

```bash
tython format src/main.ty
tython format src/
```

## Notes

- Formatting is strict.
- Invalid syntax stops the formatter with an error.
- Use formatting before review and before asking AI tools to edit code.

