# Common Patterns

## Make State Explicit

Use `var` for mutable state and `const` for stable values.

```txt
const MAX_RETRIES: int = 3
var retry_count: int = 0
```

## Keep Branches Small

```txt
if ready {
    print("go")
} else {
    print("wait")
}
```

## Prefer Named Construction

```txt
record User {
    name: str
    age: int
}

const user = User {
    name: "Ava"
    age: 31
}
```

## Use Explicit Errors

```txt
func parse_count(text: str) -> int throws ParseError {
    raise ParseError {
        message: "bad count"
    }
}
```

