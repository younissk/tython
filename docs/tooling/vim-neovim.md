# Vim and Neovim

Tython ships small editor integration files.

## Vim

```bash
tython lsp install vim
```

This installs:

- filetype detection for `*.ty`
- Vim syntax highlighting
- classic Vim LSP glue

If you want to wire it by hand:

```vim
packadd lsp
packadd tython-vim
filetype plugin on
```

## Neovim

```bash
tython lsp install nvim
```

Neovim uses builtin LSP config.

## Override Command

```vim
let g:tython_lsp_cmd = ['tython', 'lsp', 'start']
```

```lua
vim.g.tython_lsp_cmd = { 'tython', 'lsp', 'start' }
```

## Fast Check

Open a `.ty` file and confirm filetype:

```vim
:set filetype?
```

