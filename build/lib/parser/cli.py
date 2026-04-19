import argparse
import ast
from pathlib import Path

from .core import lower, parse_custom, parse_file
from .diagnostics import diagnostic_from_exception, persist_diagnostic_logs, render_diagnostic


def main() -> None:
    argparser = argparse.ArgumentParser()
    argparser.add_argument("filename")
    argparser.add_argument("--mode", choices=["exec", "eval", "single"], default="exec")
    argparser.add_argument(
        "--transpile",
        action="store_true",
        help="Transpile .txt custom syntax to a .py file instead of executing it.",
    )
    argparser.add_argument(
        "-o",
        "--output",
        help="Output path for --transpile (defaults to input path with .py suffix).",
    )
    argparser.add_argument(
        "--errors",
        choices=["rich", "compact", "json", "jsonl", "llm"],
        default="rich",
        help="Diagnostic rendering mode.",
    )
    argparser.add_argument(
        "--export-errors",
        help="Optional file path for exported diagnostics (jsonl payload).",
    )
    argparser.add_argument(
        "--verbose-errors",
        action="store_true",
        help="Show expanded diagnostic details.",
    )
    argparser.add_argument(
        "--trace",
        action="store_true",
        help="Include traceback details in diagnostic output.",
    )
    args = argparser.parse_args()

    file_path = Path(args.filename)

    try:
        if args.transpile:
            _run_transpile(file_path, args)
            return

        if file_path.suffix == ".txt":
            _run_custom_runtime(file_path, args)
            return

        tree = parse_file(file_path, mode=args.mode)
        print(ast.dump(tree, indent=2))
    except Exception as error:
        _report_error(error, file=str(file_path), args=args, default_phase="compile")


def _run_transpile(file_path: Path, args: argparse.Namespace) -> None:
    if file_path.suffix != ".txt":
        raise SystemExit("--transpile currently supports .txt inputs only")

    source = file_path.read_text()
    lowered = lower(parse_custom(source))
    output_path = Path(args.output) if args.output else file_path.with_suffix(".py")
    output_path.write_text(ast.unparse(lowered) + "\n")
    print(output_path)


def _run_custom_runtime(file_path: Path, args: argparse.Namespace) -> None:
    source = file_path.read_text()
    lowered = lower(parse_custom(source))
    code = compile(lowered, str(file_path), args.mode)

    try:
        if args.mode == "eval":
            print(eval(code, {"__name__": "__main__"}))
        else:
            exec(code, {"__name__": "__main__"})
    except Exception as error:
        _report_error(error, file=str(file_path), args=args, default_phase="panic")


def _report_error(
    error: Exception,
    *,
    file: str,
    args: argparse.Namespace,
    default_phase: str,
) -> None:
    diagnostic = diagnostic_from_exception(
        error,
        file=file,
        include_trace=args.trace or args.verbose_errors,
        default_phase=default_phase,
    )
    rendered = render_diagnostic(
        diagnostic,
        mode=args.errors,
        verbose=args.verbose_errors or args.trace,
    )
    print(rendered)
    persist_diagnostic_logs(diagnostic, export_path=args.export_errors)
    raise SystemExit(1)
