from __future__ import annotations

import shutil
import subprocess
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .project import (
    PackageSpec,
    ProjectManifest,
    find_project_root,
    infer_package_name,
    is_path_target,
    load_manifest,
    write_manifest,
)
from .formatter import format_file, format_source
from .lint import discover_lint_targets, lint_file
from .project_build import build_project, lock_project, run_generated_target


class ExecMode(str, Enum):
    exec = "exec"
    eval = "eval"
    single = "single"


app = typer.Typer(
    name="tython",
    invoke_without_command=True,
    no_args_is_help=True,
    add_completion=False,
    help="Minimal strict project-first CLI for Tython.",
)
lsp_app = typer.Typer(
    name="lsp", help="Language server commands.", add_completion=False
)
lsp_install_app = typer.Typer(
    name="install", help="Install LSP integrations.", add_completion=False
)
app.add_typer(lsp_app)
lsp_app.add_typer(lsp_install_app)
_console = Console()
_error_console = Console(stderr=True)

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
    let l:pyproject = findfile('pyproject.toml', expand('<sfile>:p:h') . ';')
    if !empty(l:pyproject) && executable('uv')
      let l:cmd = ['uv', 'run', '--directory', fnamemodify(l:pyproject, ':h'), 'tython-lsp']
    elseif executable('tython')
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

syntax keyword tythonKeyword const var func class record if else return true false none import pyimport
syntax match tythonType /\\<\\(int\\|float\\|bool\\|str\\)\\>/
syntax region tythonString start=/"/ end=/"/
syntax match tythonNumber /\\v<[0-9]+(\\.[0-9]+)?>/

highlight default link tythonKeyword Keyword
highlight default link tythonType Type
highlight default link tythonString String
highlight default link tythonNumber Number

let b:current_syntax = "tython"
"""

_NVIM_LSP_PLUGIN = """if vim.g.loaded_tython_nvim_lsp then
  return
end
vim.g.loaded_tython_nvim_lsp = 1

if not vim.lsp or not vim.lsp.enable then
  return
end

local function enable_tython()
  vim.lsp.enable('tython')
end

local group = vim.api.nvim_create_augroup('tython_nvim_lsp', { clear = true })

vim.api.nvim_create_autocmd('FileType', {
  group = group,
  pattern = 'tython',
  callback = enable_tython,
})

vim.api.nvim_create_autocmd('LspAttach', {
  group = group,
  callback = function(args)
    local client = vim.lsp.get_client_by_id(args.data.client_id)
    if not client or client.name ~= 'tython' then
      return
    end

    vim.api.nvim_create_autocmd('BufWritePre', {
      group = group,
      buffer = args.buf,
      callback = function()
        vim.lsp.buf.format({
          async = false,
          timeout_ms = 5000,
          filter = function(format_client)
            return format_client.name == 'tython'
          end,
        })
      end,
    })
  end,
})

vim.schedule(enable_tython)
"""

_NVIM_LSP_CONFIG = """local function checkout_root()
  local source = debug.getinfo(1, 'S').source
  if type(source) ~= 'string' or source:sub(1, 1) ~= '@' then
    return nil
  end

  local plugin_file = source:sub(2)
  local pyproject = vim.fs.find('pyproject.toml', {
    path = vim.fs.dirname(plugin_file),
    upward = true,
  })[1]
  if pyproject == nil then
    return nil
  end
  return vim.fs.dirname(pyproject)
end

local function default_cmd()
  local repo_root = checkout_root()
  if repo_root ~= nil and vim.fn.executable('uv') == 1 then
    return { 'uv', 'run', '--directory', repo_root, 'tython-lsp' }
  end
  if vim.fn.executable('tython') == 1 then
    return { 'tython', 'lsp', 'start' }
  end
  if vim.fn.executable('tython-lsp') == 1 then
    return { 'tython-lsp' }
  end
  return { 'uv', 'run', 'tython-lsp' }
end

local cmd = vim.g.tython_lsp_cmd
if type(cmd) ~= 'table' or vim.tbl_isempty(cmd) then
  cmd = default_cmd()
end

return {
  name = 'tython-lsp',
  cmd = cmd,
  filetypes = { 'tython' },
  root_markers = { 'project.toml', '.git' },
}
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


def _install_editor_package(pack_root: Path) -> Path:
    package_root = pack_root / "tython" / "start" / "tython-vim"
    (package_root / "ftdetect").mkdir(parents=True, exist_ok=True)
    (package_root / "plugin").mkdir(parents=True, exist_ok=True)
    (package_root / "syntax").mkdir(parents=True, exist_ok=True)
    (package_root / "lsp").mkdir(parents=True, exist_ok=True)

    (package_root / "ftdetect" / "tython.vim").write_text(_VIM_FTDETECT)
    (package_root / "plugin" / "tython_lsp.vim").write_text(_VIM_PLUGIN)
    (package_root / "plugin" / "tython_lsp.lua").write_text(_NVIM_LSP_PLUGIN)
    (package_root / "syntax" / "tython.vim").write_text(_VIM_SYNTAX)
    (package_root / "lsp" / "tython.lua").write_text(_NVIM_LSP_CONFIG)
    return package_root


@app.callback()
def root(
    version_flag: bool = typer.Option(
        False, "--version", help="Show version and exit.", is_eager=True
    ),
) -> None:
    if version_flag:
        _console.print(f"tython {_resolve_version()}")
        raise typer.Exit()


@app.command(help="Initialize minimal Tython project in current directory.")
def init(
    name: str = typer.Option("my_app", "--name", help="Project/package name."),
    force: bool = typer.Option(
        False, "--force", help="Overwrite project.toml and src/main.ty if present."
    ),
) -> None:
    project_root = Path.cwd()
    src_dir = project_root / "src"
    tython_dir = project_root / ".tython"
    build_dir = tython_dir / "build"
    cache_dir = tython_dir / "cache"
    project_file = project_root / "project.toml"
    main_file = src_dir / "main.ty"

    src_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if project_file.exists() and not force:
        _error(
            f"{project_file} already exists",
            "Use `tython init --force` to overwrite, or keep existing project.",
        )
    if main_file.exists() and not force:
        _error(
            f"{main_file} already exists",
            "Use `tython init --force` to overwrite, or keep existing source.",
        )

    project_file.write_text(
        f"""[project]
name = "{name}"
version = "0.1.0"
entry = "src/main.ty"

[python]
dependencies = [
]
"""
    )
    main_file.write_text(format_source('print("hello from tython")\n'))
    _console.print(f"[green]Initialized[/green] {project_root}")


@app.command(help="Add native package (git URL) or Python dependency (--py).")
def add(
    spec: str = typer.Argument(..., help="Git URL or Python dependency spec."),
    py: bool = typer.Option(False, "--py", help="Treat spec as Python dependency."),
    name: str | None = typer.Option(
        None, "--name", help="Explicit package name for native dependency."
    ),
    rev: str = typer.Option(
        "", "--rev", help="Exact 40-char git commit SHA for native dependency."
    ),
) -> None:
    project_root = find_project_root(Path.cwd())
    manifest = load_manifest(project_root)

    if py:
        if not spec.strip():
            _error(
                "Python dependency spec cannot be empty",
                "Pass dependency like `requests>=2.32`.",
            )
        if spec in manifest.python_dependencies:
            _console.print(f"[yellow]Exists[/yellow] python dependency {spec}")
            return
        write_manifest(
            project_root,
            ProjectManifest(
                name=manifest.name,
                version=manifest.version,
                entry=manifest.entry,
                packages=manifest.packages,
                python_dependencies=[*manifest.python_dependencies, spec],
            ),
        )
        _console.print(f"[green]Added[/green] python dependency {spec}")
        return

    if not rev:
        _error(
            "Native package requires --rev", "Pass exact 40-char commit SHA with --rev."
        )

    package_name = name or infer_package_name(spec)
    if package_name in manifest.packages:
        _error(
            f"Package '{package_name}' already exists",
            "Use --name for a different alias.",
        )

    updated_packages = dict(manifest.packages)
    updated_packages[package_name] = PackageSpec(
        name=package_name, git=spec, requested=rev
    )
    write_manifest(
        project_root,
        ProjectManifest(
            name=manifest.name,
            version=manifest.version,
            entry=manifest.entry,
            packages=updated_packages,
            python_dependencies=manifest.python_dependencies,
        ),
    )
    _console.print(f"[green]Added[/green] package {package_name} ({spec}@{rev})")


@app.command(help="Resolve native git deps and write project.lock.")
def lock() -> None:
    project_root = find_project_root(Path.cwd())
    lock_data = lock_project(project_root)
    _console.print(f"[green]Wrote[/green] {project_root / 'project.lock'}")
    _console.print(f"Locked {len(lock_data.packages)} package(s)")


@app.command(help="Build project into .tython/build Python package.")
def build() -> None:
    project_root = find_project_root(Path.cwd())
    build_root = build_project(project_root)
    _console.print(f"[green]Built[/green] {build_root}")


@app.command(help="Lint Tython source files in current project.")
def lint(
    paths: list[Path] = typer.Argument(
        [],
        help="Optional .ty files or directories. Defaults to src/ in project root.",
    ),
) -> None:
    project_root = find_project_root(Path.cwd())
    try:
        targets = discover_lint_targets(project_root, paths)
    except SyntaxError:
        _error("src/ directory missing", "Create src/ or pass explicit files to lint.")
    has_errors = False
    checked = 0

    for path in targets:
        checked += 1
        diagnostics = lint_file(path)
        if diagnostics:
            has_errors = True
            for diagnostic in diagnostics:
                _error_console.print(diagnostic)

    if has_errors:
        raise typer.Exit(code=1)

    _console.print(f"[green]Linted[/green] {checked} file(s)")


@app.command(help="Format Tython source files in current project.")
def format(
    paths: list[Path] = typer.Argument(
        [],
        help="Optional .ty files or directories. Defaults to src/ in project root.",
    ),
) -> None:
    project_root = find_project_root(Path.cwd())
    targets = _format_targets(project_root, paths)
    changed = 0

    for path in targets:
        try:
            if format_file(path):
                changed += 1
        except SyntaxError as exc:
            _error(str(exc), f"Fix syntax in {path} and retry.")

    _console.print(f"[green]Formatted[/green] {changed} file(s)")


@app.command(help="Run .ty path in project context. Tasks removed in minimal mode.")
def run(
    target: str | None = typer.Argument(
        None, help=".ty path under src/ (defaults to [project].entry)"
    ),
    mode: ExecMode = typer.Option(
        ExecMode.exec, "--mode", help="Execution mode for path target."
    ),
) -> None:
    project_root = find_project_root(Path.cwd())
    manifest = load_manifest(project_root)

    resolved_target = target or manifest.entry

    if not is_path_target(resolved_target):
        _error(
            f"Invalid run target '{resolved_target}'",
            "Use .ty path under src/ or set [project].entry to .ty path.",
        )

    path = Path(resolved_target)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    src_root = (project_root / "src").resolve()
    if src_root not in path.parents and path != src_root:
        _error(f"Path target must live under src/: {path}", "Pass .ty path under src/.")
    if path.suffix != ".ty":
        _error(
            f"Unsupported path extension: {path.suffix or '(none)'}",
            "Pass .ty path under src/.",
        )
    if not path.exists():
        _error(f"Target file not found: {path}", "Pass existing .ty source path.")

    try:
        run_generated_target(project_root, path, mode=mode.value)
    except Exception as exc:
        _error(str(exc), "Fix project/dependency config and retry.")


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
    tython_vim_root = _install_editor_package(vim_pack_root)

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

    _console.print("[green]Done[/green] Restart Vim and open .ty file.")


@lsp_install_app.command("nvim", help="Install built-in Neovim LSP support for Tython.")
def lsp_install_nvim(
    nvim_pack_root: Path = typer.Option(
        Path.home() / ".local" / "share" / "nvim" / "site" / "pack",
        "--nvim-pack-root",
        help="Neovim package root directory.",
    ),
) -> None:
    tython_nvim_root = _install_editor_package(nvim_pack_root)

    _console.print(f"[green]Installed[/green] {tython_nvim_root}")
    _console.print("[green]Done[/green] Restart Neovim and open .ty file.")


def _format_targets(project_root: Path, paths: list[Path]) -> list[Path]:
    if not paths:
        src_root = project_root / "src"
        if not src_root.exists():
            _error(
                "src/ directory missing",
                "Create src/ or pass explicit files to format.",
            )
        return sorted(src_root.rglob("*.ty"))

    targets: list[Path] = []
    for raw in paths:
        path = raw if raw.is_absolute() else (project_root / raw).resolve()
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.ty")))
            continue
        if path.suffix == ".ty":
            targets.append(path)
    return targets


def main() -> None:
    app()


if __name__ == "__main__":
    main()
