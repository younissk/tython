from dataclasses import dataclass


@dataclass(frozen=True)
class Animal:
    name: str


class Fish:
    def __init__(self, *, name: str) -> None:
        self.name = name
        self.age = 1
        self.age = self.age + 1

    def speak(self) -> None:
        print(self.name)


FISH = Fish(name="Nemo")
ANIMAL = Animal(name="Nemo")
