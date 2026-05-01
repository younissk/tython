![tyhon banner](./tython-banner.png)

# Tython

Just a small language I designed as a fun side project.

P.S. mascott doesnt have a name yet. Please help me name it

## Syntax

The Langauge is designed to help us humans and LLMs theoretically understand code better. Therefore it is:

- Statically typed
- Highly opinionated
- Standardised
- Token efficient??? maybe

Here a bit of a taste of the language: 

```tython
record Animal {
  NAME: str,
  hello(name: str) -> none
}

class Fish is Animal{

  init const NAME: str
  
  pub func hello(name: str) -> none {
    print("Hello {name}, my name is {this.NAME}")
  }

}

const FISH = Fish(name: "tom")
FISH.hello("jerry")
```

`init` variables in a class just bypass this syntax: `self.name = name` and also `this` is arguably better than passing `self` in every method. Methods by default are private, unless you add `pub` infront of it. Everything is statically typed and also I added consts and vars for mutibility stuff.

## TODO

### Docs

- Go over to see if llms generated it correctly
- make a nicer design and front page (I like the ghostty one)

### Standard library

A language without a standard library is usually painful to use.

Typical standard library areas:

- files (Glob under the hood?)
- networking
- math (Numpy?)
- centralized testing framework (like bun, integrated into the language)
- package registry
- binary distribution story
- how users install the language
- logging (Loguru under the hood?)

Possibly in the future:
- What about using polars by default for dataframes?
- Pytorch fully integrated in the langauge?
