.PHONY: format check test repl vim-install all

format:
	uv run ruff format .

check:
	uv run ruff format --check .
	uv run ruff check .

test:
	uv run python -m pytest

repl:
	uv run python -m parser.repl

vim-install:
	mkdir -p "$(HOME)/.vim/pack/tython/start"
	ln -sfn "$(CURDIR)/tython-vim" "$(HOME)/.vim/pack/tython/start/tython-vim"

all: check test
