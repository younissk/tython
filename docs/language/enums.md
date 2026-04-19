# Enums

Tython supports enum declarations with explicit members.

## Enum Declaration

```txt
enum Habitat {
    ocean
    forest
}
```

Members must be valid identifiers.

Empty enums are rejected.

## Using Enum Values

```txt
enum Habitat {
    ocean
    forest
}

var current: Habitat = Habitat.ocean
```

## Lowering Behavior

Enums lower to Python `Enum` classes in transpiled output.

Equivalent Python shape:

```python
from enum import Enum

class Habitat(Enum):
    ocean = "ocean"
    forest = "forest"
```
