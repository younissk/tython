from __future__ import annotations

import ast
import shutil
import subprocess
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .core import lower, parse_custom
from .repl import main as repl_main


class ExecMode(str, Enum):
    exec = "exec"
    eval = "eval"
    single = "single"


app = typer.Typer(
    name="tython",
    invoke_without_command=True,
    no_args_is_help=True,
    add_completion=False,
    help="A small, strict CLI for running and transpiling Tython files.",
)
lsp_app = typer.Typer(
    name="lsp",
    help="Language server commands.",
    add_completion=False,
)
lsp_install_app = typer.Typer(
    name="install",
    help="Install LSP integrations.",
    add_completion=False,
)
app.add_typer(lsp_app)
lsp_app.add_typer(lsp_install_app)
_console = Console()
_error_console = Console(stderr=True)
_ALLOWED_SUFFIXES = {".txt", ".ty"}
_VIM_FTDETECT = """augroup tython_ftdetect
  autocmd!
  autocmd BufRead,BufNewFile *.ty setfiletype tython
augroup END
"""
_VIM_PLUGIN = """if exists('g:loaded_tython_lsp')
  finish
endif
let g:loaded_tython_lsp = 1

let s:server_registered = 0

function! s:RegisterTythonLsp() abort
  if s:server_registered
    return
  endif
  if !exists('*LspAddServer')
    silent! packadd lsp
  endif
  if !exists('*LspAddServer')
    return
  endif

  let l:cmd = get(g:, 'tython_lsp_cmd', [])
  if empty(l:cmd)
    if executable('tython')
      let l:cmd = ['tython', 'lsp', 'start']
    elseif executable('tython-lsp')
      let l:cmd = ['tython-lsp']
    else
      let l:cmd = ['uv', 'run', 'tython-lsp']
    endif
  endif

  call LspAddServer([#{
        \\ name: 'tython-lsp',
        \\ filetype: ['tython'],
        \\ path: l:cmd[0],
        \\ args: l:cmd[1:],
        \\ traceLevel: 'debug'
        \\ }])
  let s:server_registered = 1
endfunction

augroup tython_lsp
  autocmd!
  autocmd BufRead,BufNewFile *.ty setfiletype tython
  autocmd VimEnter * call <SID>RegisterTythonLsp()
  autocmd FileType tython call <SID>RegisterTythonLsp()
  autocmd FileType tython if exists(':LspHover') | setlocal keywordprg=:LspHover | nnoremap <buffer> K :LspHover<CR> | endif
  autocmd FileType tython if exists(':LspDiag') | nnoremap <buffer> <leader>e :LspDiag current<CR> | endif
augroup END
"""
_VIM_SYNTAX = """if exists("b:current_syntax")
  finish
endif

syntax keyword tythonKeyword const var func class record if else return true false none
syntax match tythonType /\\<\\(int\\|float\\|bool\\|str\\)\\>/
syntax region tythonString start=/"/ end=/"/
syntax match tythonNumber /\\v<[0-9]+(\\.[0-9]+)?>/

highlight default link tythonKeyword Keyword
highlight default link tythonType Type
highlight default link tythonString String
highlight default link tythonNumber Number

let b:current_syntax = "tython"
"""


def _resolve_version() -> str:
    try:
        return version("tython")
    except PackageNotFoundError:
        return "0.1.0"


def _error(message: str, hint: str) -> None:
    _error_console.print(
        Panel.fit(
            f"[bold red]Error:[/bold red] {message}\n[dim]{hint}[/dim]",
            title="tython",
            border_style="red",
        )
    )
    raise typer.Exit(code=1)


def _validate_input_path(input_path: Path) -> None:
    if not input_path.exists():
        _error(
            f"Input file not found: {input_path}",
            "Pass a valid path to a .txt or .ty file.",
        )

    if not input_path.is_file():
        _error(
            f"Input path is not a file: {input_path}",
            "Pass a file path ending in .txt or .ty.",
        )

    if input_path.suffix.lower() not in _ALLOWED_SUFFIXES:
        _error(
            f"Unsupported input extension: {input_path.suffix or '(none)'}",
            "Only .txt and .ty files are supported.",
        )


@app.callback()
def root(
    version_flag: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        is_eager=True,
    ),
) -> None:
    if version_flag:
        _console.print(f"tython {_resolve_version()}")
        raise typer.Exit()


@app.command(help="Run a Tython file (.txt or .ty).")
def run(
    input_path: Path = typer.Argument(
        ..., metavar="INPUT", help="Path to .txt or .ty file."
    ),
    mode: ExecMode = typer.Option(ExecMode.exec, "--mode", help="Compile mode."),
) -> None:
    _validate_input_path(input_path)

    try:
        source = input_path.read_text()
        lowered = lower(parse_custom(source))
        code = compile(lowered, str(input_path), mode.value)

        if mode is ExecMode.eval:
            result = eval(code, {"__name__": "__main__"})
            if result is not None:
                _console.print(result)
            return

        exec(code, {"__name__": "__main__"})
    except Exception as exc:
        _error(
            f"Failed to run {input_path.name}: {exc}",
            "Fix the source file and try again.",
        )


@app.command(help="Transpile a Tython file (.txt or .ty) to a Python file.")
def transpile(
    input_path: Path = typer.Argument(
        ..., metavar="INPUT", help="Path to .txt or .ty file."
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .py path. Defaults to input path with .py suffix.",
    ),
) -> None:
    _validate_input_path(input_path)

    output_path = output if output is not None else input_path.with_suffix(".py")

    try:
        source = input_path.read_text()
        lowered = lower(parse_custom(source))
        output_path.write_text(ast.unparse(lowered) + "\n")
        _console.print(f"[green]Wrote[/green] {output_path}")
    except Exception as exc:
        _error(
            f"Failed to transpile {input_path.name}: {exc}",
            "Fix the source file and try again.",
        )


@app.command(help="Start the interactive Tython REPL.")
def repl() -> None:
    repl_main()


@app.command("version", help="Show CLI version.")
def cli_version() -> None:
    _console.print(f"tython {_resolve_version()}")


@lsp_app.command("start", help="Start the Tython language server over stdio.")
def lsp_start() -> None:
    from .lsp.server import main as lsp_main

    lsp_main()


@lsp_install_app.command("vim", help="Install classic Vim support for Tython LSP.")
def lsp_install_vim(
    vim_pack_root: Path = typer.Option(
        Path.home() / ".vim" / "pack",
        "--vim-pack-root",
        help="Vim package root directory.",
    ),
    install_lsp_plugin: bool = typer.Option(
        True,
        "--install-lsp-plugin/--no-install-lsp-plugin",
        help="Install yegappan/lsp if missing.",
    ),
) -> None:
    tython_vim_root = vim_pack_root / "tython" / "start" / "tython-vim"
    (tython_vim_root / "ftdetect").mkdir(parents=True, exist_ok=True)
    (tython_vim_root / "plugin").mkdir(parents=True, exist_ok=True)
    (tython_vim_root / "syntax").mkdir(parents=True, exist_ok=True)

    (tython_vim_root / "ftdetect" / "tython.vim").write_text(_VIM_FTDETECT)
    (tython_vim_root / "plugin" / "tython_lsp.vim").write_text(_VIM_PLUGIN)
    (tython_vim_root / "syntax" / "tython.vim").write_text(_VIM_SYNTAX)

    _console.print(f"[green]Installed[/green] {tython_vim_root}")

    if install_lsp_plugin:
        lsp_root = vim_pack_root / "lsp" / "start" / "lsp"
        if lsp_root.exists():
            _console.print(f"[yellow]Exists[/yellow] {lsp_root}")
        else:
            git_bin = shutil.which("git")
            if git_bin is None:
                _console.print(
                    "[yellow]Skipped[/yellow] yegappan/lsp install (git not found)."
                )
            else:
                lsp_root.parent.mkdir(parents=True, exist_ok=True)
                completed = subprocess.run(
                    [
                        git_bin,
                        "clone",
                        "https://github.com/yegappan/lsp",
                        str(lsp_root),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    _error(
                        f"Failed to install yegappan/lsp: {completed.stderr.strip() or 'git clone failed'}",
                        "Install manually: git clone https://github.com/yegappan/lsp ~/.vim/pack/lsp/start/lsp",
                    )
                _console.print(f"[green]Installed[/green] {lsp_root}")

    _console.print("[green]Done[/green] Restart Vim and open a .ty file.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
