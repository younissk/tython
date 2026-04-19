# Records and Classes

Tython v1 separates immutable data shapes (`record`) from stateful objects (`class`).

## Design Rules

- `record` is immutable and value-like.
- `class` is stateful and method-oriented.
- No inheritance: no `extends`, no `super`.
- Visibility is private-by-default; use `pub` for public members.
- Class constructor API comes from `init` fields.
- Post-construction logic lives in a single optional `setup` block.
- Class conformance to a record uses `is` (one record max in v1).

## Records

```txt
record Animal {
    name: str
    speak: () -> none
}
```

Rules:

- Record members are typed fields only.
- Record members are always public.
- No `init`, `setup`, `pub`, `var`, `const`, or method bodies inside records.

Construction uses braces:

```txt
const A = Animal {
    name: "Nemo"
    speak: fish_speak
}
```

Compile-time checks enforce:

- missing required fields
- unknown fields
- duplicate fields
- type mismatches

## Classes

```txt
class Fish is Animal {
    init var name: str
    pub var age: int = 0

    setup {
        this.age = this.age + 1
    }

    pub func speak() -> none {
        print(this.name)
    }
}
```

Allowed class members:

- `init var`, `init const`
- `var`, `const`
- `pub var`, `pub const`
- `func`, `pub func`
- one optional `setup`

### Visibility

- Everything is private by default.
- `pub` makes module/class members public.
- `init var` and `init const` are always public; `pub init ...` is invalid.

### `init` fields

`init` fields define constructor parameters and create instance fields automatically.

```txt
class User {
    init const id: str
    init var name: str
}
```

Conceptual constructor API:

```txt
User(id: str, name: str)
```

Defaults are allowed for optional constructor args:

```txt
init var age: int = 0
```

### `setup`

`setup` is a lifecycle block, not a normal function:

- optional
- parameterless
- auto-run during construction
- at most one per class
- not callable manually

Initialization order:

1. assign all `init` fields from constructor args
2. assign normal field defaults
3. run `setup`

### `this`

Instance access is explicit:

- `this.name`
- `this.speak()`

Methods do not declare a receiver parameter; it is implicit.

## Class Conformance with `is`

A class may conform to one record:

```txt
class Fish is Animal {
    init var name: str

    pub func speak() -> none {
        print(this.name)
    }
}
```

Conformance checks require public members matching record requirements:

- required field names/types must exist and be public
- required function types must be satisfied by matching public methods or public callable members

## Runtime Lowering

- `record` lowers to frozen `@dataclass`.
- `class` lowers to Python class with generated keyword-only `__init__` from `init` fields.
- record literals lower to constructor calls with keywords.
