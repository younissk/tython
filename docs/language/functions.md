# Functions

Tython functions are explicit and fully typed.

## Declaration

Functions use the `func` keyword.

Block body:

```txt
func add(a: int, b: int) -> int {
    return a + b
}
```

Expression body:

```txt
func add(a: int, b: int) -> int = a + b
```

## Core Rules

- Function names must be snake_case.
- Every parameter requires a type annotation.
- Every function requires an explicit return type.
- Function declarations are allowed only at module scope.
- Nested function declarations are rejected.
- Lambdas are not supported.

## Parameters and Defaults

Defaults are supported, but required parameters must come first.

```txt
func greet(name: str, title: str = "Mr") -> str = title + " " + name
```

Invalid:

```txt
func greet(title: str = "Mr", name: str) -> str = title + " " + name
```

## Calls

Call forms:

- fully positional: `add(1, 2)`
- fully named: `greet(name: "Youniss", title: "Dr")`

Mixing positional + named is rejected.

Named arguments can appear in any order.

## Returns

- Non-`none` functions must return a value on every reachable path.
- `none` functions may fall off the end.
- Use `return none` when returning explicitly from a `none` function.

## Function Types

Function type syntax is supported in annotations:

```txt
(name: str, title: str) -> str
```

Parameter names are part of the function type surface in this phase.
