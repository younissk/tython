def add(a: int, b: int) -> int:
    return a + b


def greet(name: str, title: str = "Mr") -> str:
    return title + " " + name


x = add(1, 2)
y = greet(title="Dr", name="Youniss")
