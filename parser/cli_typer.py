from __future__ import annotations

import ast
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
_console = Console()
_error_console = Console(stderr=True)
_ALLOWED_SUFFIXES = {".txt", ".ty"}


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
    input_path: Path = typer.Argument(..., metavar="INPUT", help="Path to .txt or .ty file."),
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
    input_path: Path = typer.Argument(..., metavar="INPUT", help="Path to .txt or .ty file."),
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
