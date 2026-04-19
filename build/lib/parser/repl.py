from __future__ import annotations

import ast

from .core import lower
from .custom_frontend import parse_custom_source
from .diagnostics import diagnostic_from_exception, render_diagnostic
from .semantics import check_semantics_with_prelude


def main() -> None:
    print("Tython REPL")
    print("Enter code. Use :quit to exit, :reset to clear state.")

    globals_ns: dict[str, object] = {"__name__": "__main__"}
    declared: dict[str, tuple[str, str | None, bool]] = {}
    buffer: list[str] = []
    brace_depth = 0

    while True:
        prompt = "... " if buffer else ">>> "
        try:
            line = input(prompt)
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            buffer.clear()
            brace_depth = 0
            continue

        stripped = line.strip()
        if not buffer and stripped in {":quit", ":exit"}:
            break
        if not buffer and stripped == ":reset":
            globals_ns = {"__name__": "__main__"}
            declared = {}
            print("state reset")
            continue

        buffer.append(line)
        brace_depth += _brace_delta(line)

        source = "\n".join(buffer).rstrip() + "\n"
        if brace_depth > 0:
            continue

        try:
            frontend = parse_custom_source(source)
            next_declared = check_semantics_with_prelude(frontend.tree, declared)
            tree = frontend.tree
            lowered = lower(tree)
            _execute(lowered, source, globals_ns)
            declared = next_declared
            buffer.clear()
            brace_depth = 0
        except SyntaxError as error:
            if _is_incomplete_input(error):
                continue
            diagnostic = diagnostic_from_exception(
                error,
                file="<repl>",
                include_trace=False,
                default_phase="compile",
            )
            print(render_diagnostic(diagnostic, mode="rich", verbose=False))
            buffer.clear()
            brace_depth = 0
        except Exception as error:  # pragma: no cover - interactive behavior
            diagnostic = diagnostic_from_exception(
                error,
                file="<repl>",
                include_trace=False,
                default_phase="panic",
            )
            print(render_diagnostic(diagnostic, mode="rich", verbose=False))
            buffer.clear()
            brace_depth = 0


def _execute(tree: ast.AST, source: str, namespace: dict[str, object]) -> None:
    if not isinstance(tree, ast.Module):
        code = compile(tree, "<repl>", "exec")
        exec(code, namespace)
        return

    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
        expr = tree.body[0].value
        expr_code = compile(ast.Expression(body=expr), "<repl>", "eval")
        value = eval(expr_code, namespace)
        if value is not None:
            print(repr(value))
        return

    code = compile(tree, "<repl>", "exec")
    exec(code, namespace)


def _brace_delta(line: str) -> int:
    return line.count("{") - line.count("}")


def _is_incomplete_input(error: SyntaxError) -> bool:
    text = str(error)
    return (
        "unexpected EOF while parsing" in text
        or "was never closed" in text
        or "expected an indented block" in text
    )


if __name__ == "__main__":
    main()
