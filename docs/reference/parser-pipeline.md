# Parser Pipeline

This page describes how custom Tython syntax is processed internally.

## `parse_custom` Flow

1. Normalize source input.
2. Rewrite custom syntax:
   - brace blocks (`{}`)
   - `func` declarations
   - checked error syntax (`throws`, `catch`, `try expr`)
   - `record` declarations and literals
   - `class` declarations (`init`, `setup`, `pub`, `is`)
   - enums
   - `const` / `var` binding declarations
   - lowercase literals (`true`, `false`, `none`)
3. Parse rewritten code into Python AST.
4. Run semantic checks (scope, naming, mutability, declarations, conservative typing, class/record conformance).
5. Lower custom IR nodes (bindings, enums, records/classes, record literals) into final Python AST.

## Stable Public API

The parser-facing API remains:

- `parse`
- `parse_custom`
- `lower`

from `parser/core.py`.
