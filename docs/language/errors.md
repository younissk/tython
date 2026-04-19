# Errors and Rejections

Tython rejects ambiguous or risky constructs at compile time.

## Common Rejections

- Using a name before declaration
- Assigning to an undeclared name
- Reassigning a `const`
- Missing initializer in `const` or `var` declaration
- Declaring the same name twice in one scope
- Shadowing outer local names in nested scopes
- Invalid naming format for const/var/type names
- Mixed-type list literals
- Incompatible initializer type for declared annotation
- Empty blocks without `pass`
- `for` loop usage in v1
- `break`/`continue` outside loops
- Unreachable statements after `return`/`break`/`continue`
- Non-call standalone expression statements
- Invalid ternary condition/type or malformed ternary usage

## Examples

### Invalid `const` naming

```txt
const max_users = 100   // invalid
```

### Invalid reassignment

```txt
const MAX = 10
MAX = 11   // invalid
```

### Missing initializer

```txt
var count   // invalid
```

### Undeclared assignment

```txt
x = 5   // invalid
```

### Shadowing

```txt
var count = 0
if true {
    var count = 1   // invalid
}
```

## Error Philosophy

Errors are designed to be deterministic and early.

When in doubt, Tython chooses rejection over implicit behavior.

## Error Message Format

Tython errors use a structured format:

```txt
[EXXXX] Line N: message. Hint: actionable next step
```

Example:

```txt
[E2022] Line 2: name 'count' is declared but not initialized. Hint: Initialize it before reading, e.g. `count = value`.
```
