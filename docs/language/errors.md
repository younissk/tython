# Errors and Diagnostics

Tython separates recoverable runtime errors from unrecoverable crashes.

## Recoverable Errors (Checked)

Recoverable errors are typed record values.

```txt
record FileError {
    path: str
    reason: str
}
```

Functions that may emit recoverable errors must declare them with `throws`:

```txt
func read_file(path: str) -> str throws FileError {
    raise FileError {
        path: path
        reason: "not found"
    }
}
```

### Rules

- `raise` is checked.
- A function/method may raise only error record types declared in its `throws` clause.
- Throwing calls must be explicit:
  - Use `try fn(...)` to propagate outward.
  - Or call inside `try { ... } catch ...` where the thrown type is handled.
- `throws` is supported for module functions and class methods.

## Handling Errors

Use `try` / `catch` / `finally`.

```txt
try {
    var text = read_file("notes.txt")
    print(text)
} catch err: FileError {
    print(err.reason)
} catch any {
    print("fallback")
} finally {
    print("done")
}
```

### Catch rules

- Typed catch: `catch err: FileError { ... }`
- Catch-all: `catch err { ... }`
- Catch-all must be last.
- Typed matching is exact by record type.

## Panic (Unrecoverable)

Use `panic("message")` for invariant violations and unrecoverable states.

- Panic is not part of `throws`.
- Panic is not recoverable by `catch`.

## Diagnostic Model

Compiler/runtime failures are represented as structured diagnostics.

Required fields include:

- `code`
- `severity`
- `phase`
- `message`
- `file`
- `range`
- `timestamp`

The published schema is versioned and documented in [Diagnostic Schema](../reference/diagnostic-schema.md).

The published error-code inventory is documented in [Error Code Catalog](../reference/error-codes.md).

## Diagnostic Rendering

Diagnostics are rendered by tools that run the compiler pipeline, such as:

- `tython lint`
- `tython run`
- `tython repl`

Editor integrations receive the same structured diagnostic payload through LSP.
The machine-readable schema is documented in [Diagnostic Schema](../reference/diagnostic-schema.md).

## Legacy Message Compatibility

Internal diagnostics still preserve the legacy user-facing message format:

```txt
[EXXXX] Line N: message. Hint: actionable next step
```
