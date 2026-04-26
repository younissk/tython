# Values and Bindings

## Design Goals

Tython prefers explicit, deterministic rules over permissive behavior.

If a construct could create ambiguity or accidental mutation, it is rejected.

## Primitive Types

Built-in primitive types:

- `int`
- `float`
- `bool`
- `str`
- `none`

## Literal Forms

- Integers: `0`, `1`, `42`, `-7`
- Floats: `0.0`, `3.14`, `-1.5`
- Booleans: `true`, `false`
- None: `none`
- Strings: `"hello"`, `"abc"`

All boolean and none literals are lowercase.

## List Types and Literals

List type syntax:

- `int[]`
- `str[]`
- `Fish[]`

List literals:

- `[]`
- `[1, 2, 3]`
- `["a", "b"]`

Mixed-type list literals are rejected:

```txt
[1, "a", true]  // invalid
```

## Bindings

There are only two binding kinds:

- `const`
- `var`

No implicit declarations.
No `let`.

### Declaration Syntax

```txt
const MAX_USERS = 100
var count = 0

const MAX_USERS: int = 100
var names: str[] = ["a", "b"]
```

Bindings may be declared in either form:

- with initializer (`name = value`)
- without initializer only when a type annotation is present (`name: Type`)

Typed empty declarations are allowed:

```txt
var count: int
count = 1

const MAX_USERS: int
MAX_USERS = 100   // first assignment is allowed
```

Without a type annotation, empty declarations are rejected.

## Mutability Rules

- `const` cannot be reassigned.
- `var` can be reassigned.

For `const` declared without initializer, the first assignment initializes it. Any later assignment is rejected.

```txt
const MAX = 10
MAX = 11   // invalid

var count = 0
count = 1  // valid
```

## Naming Rules

Identifiers are case-sensitive.

- `const` names must be `UPPER_SNAKE_CASE`.
  - Regex: `^[A-Z][A-Z0-9_]*$`
- `var` names must be `snake_case`.
  - Regex: `^[a-z][a-z0-9_]*$`
- User-defined type names must be `PascalCase`.
  - Regex: `^[A-Z][A-Za-z0-9]*$`

## Reserved Words

Reserved keywords:

- `const`
- `var`
- `pub`
- `record`
- `class`
- `setup`
- `init`
- `is`
- `this`
- `throws`
- `catch`
- `panic`
- `true`
- `false`
- `none`

Built-in type names are reserved:

- `int`
- `float`
- `bool`
- `str`
- `none`

Built-in value names are predeclared and cannot be redefined:

- `print`
- `len`
- `range`
- `panic`
- `Matrix`
