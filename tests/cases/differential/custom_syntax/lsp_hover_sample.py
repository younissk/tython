from dataclasses import dataclass


@dataclass(frozen=True)
class Animal:
    name: str


fish: Animal = Animal(name="Nemo")
