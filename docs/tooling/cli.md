# CLI

`tython` is the project-first command entrypoint.

## Main Commands

```bash
tython init
tython add https://github.com/example/pkg.tython --rev <sha>
tython add requests>=2.32 --py
tython lock
tython build
tython lint
tython format
tython run src/main.ty
tython version
```

## What Each Command Does

- `init` creates `project.toml`, `src/main.ty`, and `.tython/`.
- `add` records native git deps or passthrough Python deps.
- `lock` resolves native deps into `project.lock`.
- `build` materializes generated Python into `.tython/build/`.
- `lint` checks Tython source with the semantic checker.
- `format` rewrites Tython source to the repo formatter style.
- `run` executes a `.ty` entry under project context.
- `version` prints CLI version.

## LSP Subcommands

```bash
tython lsp start
tython lsp install vim
tython lsp install nvim
```

`tython lsp start` speaks stdio LSP.
`install vim` and `install nvim` copy editor support files into the local package path.

