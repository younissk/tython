# Quickstart

This page shows the core Tython style and rules you need to write code correctly.

## First Program

```txt
const MAX_USERS: int = 100
var count = 0

if true {
    count = count + 1
}
```

## Mental Model

- Declare every name before use.
- Choose mutability at declaration time:
  - `const` = cannot be reassigned
  - `var` = can be reassigned
- Use explicit lexical blocks.
- Avoid shadowing and implicit behavior.

## Syntax Highlights

- Lowercase literals: `true`, `false`, `none`
- Typed list annotations: `str[]`, `int[]`, `Fish[]`
- Explicit blocks with braces: `if ... { ... }`
- Functions use `func` keyword:
- Records and classes:
  - `record` for immutable named shapes
  - `class` for stateful behavior with `init` + optional `setup`

```txt
func add(a: int, b: int) -> int {
    return a + b
}
```

## Run and Transpile

Run tests:

```bash
uv run python -m pytest
```

Run a `.ty` file:

```bash
uv run tython run input.ty
```

Transpile `.ty` to Python:

```bash
uv run tython transpile input.ty --output output.py
```
