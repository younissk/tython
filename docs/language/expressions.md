# Expressions and Operators

Tython expressions are strict, predictable, and statically checked.

## Primary Expressions

Supported primary expression forms:

- Literals: `1`, `3.14`, `true`, `false`, `none`, `"abc"`
- Identifiers: `count`, `user_name`
- Parenthesized expressions: `(a + b)`
- List literals: `[1, 2, 3]`
- Matrix literals via constructor: `Matrix([1, 2, 3])`
- Calls: `add(1, 2)`
- Field access: `user.name`
- Indexing: `items[0]`
- Ternary expressions: `if cond: x else y`

## Operator Set

### Unary

- `-x` for numeric `x` (`int` or `float`)
- `not x` for boolean `x`

`+x` is not supported.

### Arithmetic

Supported:

- `+`, `-`, `*`, `/`, `//`, `%`

Rules:

- Numeric operators require numeric operands.
- `+` supports `str + str` concatenation.
- Implicit conversion is forbidden (`"a" + 1` is invalid).
- `/` is float division.

### Comparisons

Supported:

- `==`, `!=`, `<`, `<=`, `>`, `>=`

Rules:

- Chained comparisons are not allowed (`1 < x < 10` is invalid).
- `is`, `is not`, `in`, `not in` are not supported.
- `x == none` is valid.

### Boolean

Supported keyword operators:

- `and`, `or`, `not`

All boolean operators require boolean operands.

## Conditions

`if` and `while` conditions must be `bool`.

Valid:

```txt
if count > 0 {
    print(count)
}
```

Invalid:

```txt
if count {
    print(count)
}
```

## Assignment

Assignment is statement-only.

Valid:

```txt
count = count + 1
```

Invalid:

```txt
var x = (count := 5)
```

## Expression Statements

Only call expressions are allowed as standalone statements.

Valid:

```txt
print("hello")
log_error(msg)
```

Invalid:

```txt
x + 1
if ready: 1 else 0
```

## Ternary

Tython ternary syntax is:

```txt
if cond: expr_true else expr_false
```

Rules:

- Ternary condition must be `bool`.
- Ternary is expression-only (not a standalone statement).
- When embedded in operator expressions, parenthesize it.

Valid:

```txt
var x = (if ready: 1 else 2) + 3
```

Invalid:

```txt
var x = 1 + if ready: 2 else 3
```

## Indexing

Tython indexing is strict:

- zero-based
- index expression must be `int`
- negative indexes are rejected when statically known
- slicing is not supported (`items[1:3]` is invalid)

See [Matrix](matrix.md) for Matrix-specific indexing, methods, and operator rules.

## Precedence

Tython follows Python precedence for the supported operator subset.

Call / field / index bind tighter than arithmetic and comparison operators.
