# Scope and Name Resolution

Tython uses lexical scope with strict declaration rules.

## Scope Kinds

- Module scope
- Function scope
- Block scope

Block scope exists in `if`, `else`, loops, and explicit braces.

## Rules

### Declaration Before Use

A name must be declared before it is used.

```txt
count = 1
var count = 0   // invalid
```

### No Hoisting

Names become visible only from their declaration line forward.

### No Implicit Global Assignment

Assignment to undeclared names is an error.

```txt
x = 5   // invalid
```

### No Redeclaration in the Same Scope

```txt
var count = 0
var count = 1   // invalid
```

### No Shadowing

A nested scope cannot reuse a name from an accessible outer local scope.

```txt
var count = 0
if true {
    var count = 1   // invalid
}
```

### Branch-Local Names Stay Local

Bindings declared inside a branch do not escape that branch.

```txt
if true {
    var result = 1
} else {
    var result = 2
}

result  // invalid
```

Use an outer declaration when branch results need to be shared.

## Nested Functions

Nested function declarations are not allowed in v1.

```txt
func outer() -> int {
    func inner() -> int = 1   // invalid
    return inner()
}
```
