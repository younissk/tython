.PHONY: format check test repl all

format:
	uv run ruff format .

check:
	uv run ruff format --check .
	uv run ruff check .

test:
	uv run python -m pytest

repl:
	uv run python -m parser.repl

all: check test
