# Imports

Tython uses strict, explicit import forms. There is no implicit package search and no
Python-style import syntax.

## Native Import (Project Packages)

Import a native Tython package module by path, and bind it to an alias:

```txt
import net/http as http
```

Rules:

- Path must contain at least one `/` segment.
- `as <alias>` is required.

## File Import (Relative `.ty`)

Import a `.ty` file by relative path and bind it to an alias:

```txt
import "./local/file.ty" as file
```

Rules:

- Path must start with `./` or `../`.
- `as <alias>` is required.

## Python Import (Passthrough)

Import a Python module (optionally with an alias):

```txt
pyimport json
pyimport json as json
```

This is a backend escape hatch for the generated Python code.
