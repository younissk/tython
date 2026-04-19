# Functions and Blocks

## Function Syntax

Tython uses explicit func declarations:

```txt
func add(a: int, b: int) -> int {
    return a + b
}
```

## Parameters

Function parameters are local bindings.

They follow the same naming and shadowing rules as other local bindings.

```txt
func add(a: int, b: int) -> int {
    var a = 10   // invalid: redeclaration
    return a + b
}
```

## Block Syntax

Tython uses explicit braces for blocks:

```txt
if condition {
    var x = 1
} else {
    var x = 2
}
```

Every block creates a child lexical scope.

Empty blocks are rejected; use `pass` for intentional no-op blocks:

```txt
if debug {
    pass
}
```

## Branching

Canonical branching syntax:

```txt
if ready {
    print("ok")
} else if waiting {
    print("wait")
} else {
    print("no")
}
```

`else if` is written exactly as `else if` in source and lowered to `elif`.

## Loops and Loop Control

`while` is the only loop form in v1. `for` is not supported.

`break` and `continue` are valid only inside `while` bodies.

```txt
while true {
    if done {
        break
    }
}
```

## Readability Principle

Tython favors explicit structure over compact tricks.

If a block boundary or binding lifetime is unclear, rewrite it to be explicit.
