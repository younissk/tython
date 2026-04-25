.PHONY: format check test repl corpus perf catalog vim-install nvim-install all

format:
	uv run ruff format .

check:
	uv run ruff format --check .
	uv run ruff check .

test:
	uv run python -m pytest

corpus:
	uv run python scripts/run_corpus.py check

perf:
	uv run python scripts/run_corpus.py bench --output .project/perf/corpus.json --json

repl:
	uv run python -m parser.repl

catalog:
	uv run python scripts/error_catalog.py --write docs/reference/error-codes.md

vim-install:
	mkdir -p "$(HOME)/.vim/pack/tython/start"
	ln -sfn "$(CURDIR)/tython-vim" "$(HOME)/.vim/pack/tython/start/tython-vim"

nvim-install:
	mkdir -p "$(HOME)/.local/share/nvim/site/pack/tython/start"
	ln -sfn "$(CURDIR)/tython-vim" "$(HOME)/.local/share/nvim/site/pack/tython/start/tython-vim"

all: check test
