# Small Programs

## Hello World

```txt
print("hello from tython")
```

## Simple State

```txt
var count: int = 0
count = count + 1
```

## Function

```txt
func add(a: int, b: int) -> int {
    return a + b
}
```

## Record

```txt
record Point {
    x: int
    y: int
}

const ORIGIN = Point {
    x: 0
    y: 0
}
```

## Error Handling

```txt
try {
    print("safe path")
} catch err {
    print("fallback")
}
```

