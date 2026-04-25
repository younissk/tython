from __future__ import annotations

from dataclasses import dataclass
import re

from .constants import (
    CLASS_HEADER_RE,
    CLASS_MARKER_SENTINEL,
    CLASS_MEMBER_RE,
    CLASS_MEMBER_SENTINEL,
    IDENTIFIER_RE,
    PUB_DECORATOR_SENTINEL,
    RECOVERABLE_ERROR_BASE_NAME,
    RECORD_FIELD_RE,
    RECORD_HEADER_RE,
    RECORD_MARKER_SENTINEL,
    SETUP_METHOD_NAME,
    THROWS_DECORATOR_SENTINEL,
)
from .errors import err
from .functions import rewrite_func_block_decl, rewrite_func_expression_decl
from .type_system import normalize_type_expr


@dataclass
class BlockFrame:
    lineno: int
    has_statement: bool
    kind: str


def rewrite_brace_and_functions(source: str) -> str:
    lines = source.splitlines()
    output: list[str] = []
    level = 0
    stack: list[BlockFrame] = []

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if stripped == "":
            output.append("")
            continue

        leading = stripped
        while leading.startswith("}"):
            level -= 1
            if level < 0:
                raise SyntaxError(
                    err("E1005", lineno, "unmatched '}'", "Remove extra closing brace.")
                )
            closed = stack.pop()
            if not closed.has_statement:
                raise SyntaxError(
                    err(
                        "E1016",
                        closed.lineno,
                        "empty block is not allowed",
                        "Use `pass` for intentionally empty blocks.",
                    )
                )
            leading = leading[1:].lstrip()

        if leading == "":
            continue

        if leading.startswith("function "):
            raise SyntaxError(
                err(
                    "E1006",
                    lineno,
                    "`function` keyword is not supported",
                    "Use `func` for function declarations.",
                )
            )

        if "extends" in leading or re.search(r"\bsuper\b", leading):
            raise SyntaxError(
                err(
                    "E1021",
                    lineno,
                    "inheritance is not supported in v1",
                    "Use records + class conformance with `is`, composition, or helper functions.",
                )
            )

        opens_block = leading.endswith("{")
        if opens_block:
            leading = leading[:-1].rstrip()

        if leading.startswith("else if "):
            leading = "elif " + leading[len("else if ") :]

        current_kind = stack[-1].kind if stack else "module"

        if opens_block and leading.startswith("catch "):
            if stack:
                stack[-1].has_statement = True
            output.append(("    " * level) + rewrite_catch_header(leading, lineno))
            level += 1
            stack.append(BlockFrame(lineno=lineno, has_statement=False, kind="block"))
            continue

        class_header = CLASS_HEADER_RE.fullmatch(leading) if opens_block else None
        if class_header is not None:
            if stack:
                stack[-1].has_statement = True
            class_name = class_header.group("name")
            conformance = class_header.group("record")
            pub = class_header.group("pub") is not None
            output.append(("    " * level) + f"class {class_name}:")
            output.append(
                ("    " * (level + 1))
                + f"{CLASS_MARKER_SENTINEL}({conformance!r}, {pub})"
            )
            level += 1
            stack.append(BlockFrame(lineno=lineno, has_statement=True, kind="class"))
            continue

        record_header = RECORD_HEADER_RE.fullmatch(leading) if opens_block else None
        if record_header is not None:
            if stack:
                stack[-1].has_statement = True
            record_name = record_header.group("name")
            pub = record_header.group("pub") is not None
            output.append(("    " * level) + f"class {record_name}:")
            output.append(("    " * (level + 1)) + f"{RECORD_MARKER_SENTINEL}({pub})")
            level += 1
            stack.append(BlockFrame(lineno=lineno, has_statement=True, kind="record"))
            continue

        if current_kind == "record":
            field = RECORD_FIELD_RE.fullmatch(leading)
            if field is None:
                raise SyntaxError(
                    err(
                        "E1022",
                        lineno,
                        "invalid record member",
                        "Use `name: Type` fields only inside records.",
                    )
                )
            name = field.group("name")
            type_expr = normalize_type_expr(field.group("type").strip(), lineno)
            output.append(
                ("    " * level)
                + f"{CLASS_MEMBER_SENTINEL}('record_field', {name!r}, {type_expr!r}, None, False, True, True)"
            )
            if stack:
                stack[-1].has_statement = True
            continue

        if current_kind == "class":
            if leading.startswith("pub setup"):
                raise SyntaxError(
                    err(
                        "E1023",
                        lineno,
                        "`setup` cannot be marked pub",
                        "Use bare `setup { ... }`.",
                    )
                )
            if leading.startswith("setup(") or leading.startswith("setup ->"):
                raise SyntaxError(
                    err(
                        "E1024",
                        lineno,
                        "invalid setup declaration",
                        "Use `setup { ... }` with no parameters and no return annotation.",
                    )
                )

            if opens_block and leading == "setup":
                if stack:
                    stack[-1].has_statement = True
                output.append(
                    ("    " * level) + f"def {SETUP_METHOD_NAME}(self) -> None:"
                )
                level += 1
                stack.append(
                    BlockFrame(lineno=lineno, has_statement=False, kind="setup")
                )
                continue

            member_line = rewrite_class_member_line(leading, lineno)
            if member_line is not None:
                if stack:
                    stack[-1].has_statement = True
                output.append(("    " * level) + member_line)
                continue

        if leading.startswith("pub func "):
            if opens_block:
                def_header, throws_types = rewrite_func_block_decl(
                    leading.removeprefix("pub ").strip(),
                    lineno,
                    is_method=current_kind in {"class", "setup"},
                )
                if stack:
                    stack[-1].has_statement = True
                output.append(("    " * level) + f"@{PUB_DECORATOR_SENTINEL}")
                if throws_types:
                    output.append(
                        ("    " * level) + render_throws_decorator(throws_types)
                    )
                output.append(("    " * level) + def_header)
                level += 1
                stack.append(
                    BlockFrame(
                        lineno=lineno,
                        has_statement=False,
                        kind="method" if current_kind == "class" else "block",
                    )
                )
                continue

            def_header, expr_body, throws_types = rewrite_func_expression_decl(
                leading.removeprefix("pub ").strip(),
                lineno,
                is_method=current_kind in {"class", "setup"},
            )
            if stack:
                stack[-1].has_statement = True
            output.append(("    " * level) + f"@{PUB_DECORATOR_SENTINEL}")
            if throws_types:
                output.append(("    " * level) + render_throws_decorator(throws_types))
            output.append(("    " * level) + def_header)
            output.append(("    " * (level + 1)) + f"return {expr_body}")
            continue

        if leading.startswith("func ") and not opens_block:
            def_header, expr_body, throws_types = rewrite_func_expression_decl(
                leading,
                lineno,
                is_method=current_kind == "class",
            )
            if stack:
                stack[-1].has_statement = True
            if throws_types:
                output.append(("    " * level) + render_throws_decorator(throws_types))
            output.append(("    " * level) + def_header)
            output.append(("    " * (level + 1)) + f"return {expr_body}")
            continue

        if leading.startswith("func ") and opens_block:
            def_header, throws_types = rewrite_func_block_decl(
                leading,
                lineno,
                is_method=current_kind == "class",
            )
            if stack:
                stack[-1].has_statement = True
            if throws_types:
                output.append(("    " * level) + render_throws_decorator(throws_types))
            output.append(("    " * level) + def_header)
            level += 1
            stack.append(
                BlockFrame(
                    lineno=lineno,
                    has_statement=False,
                    kind="method" if current_kind == "class" else "block",
                )
            )
            continue

        if opens_block and not leading.endswith(":"):
            leading = f"{leading}:"

        if stack:
            stack[-1].has_statement = True

        has_brace_syntax = (
            "{" in stripped or "}" in stripped or stripped.startswith("func ")
        )
        if level == 0 and not has_brace_syntax:
            output.append(line)
        else:
            output.append(("    " * level) + leading)

        if opens_block:
            level += 1
            stack.append(BlockFrame(lineno=lineno, has_statement=False, kind="block"))

    if level != 0:
        raise SyntaxError(
            err(
                "E1007",
                len(lines) or 1,
                "unclosed '{' block",
                "Close every opened block with '}'.",
            )
        )

    return "\n".join(output) + "\n"


def rewrite_class_member_line(leading: str, lineno: int) -> str | None:
    member = CLASS_MEMBER_RE.fullmatch(leading)
    if member is None:
        return None

    is_pub = member.group("pub") is not None
    is_init = member.group("init") is not None
    kind = member.group("kind")
    name = member.group("name")
    type_expr = member.group("type")
    expr = member.group("expr")

    if is_init and is_pub:
        raise SyntaxError(
            err(
                "E1025",
                lineno,
                "init fields are already public and cannot use `pub`",
                "Use `init var ...` or `init const ...`.",
            )
        )

    normalized_type: str | None = None
    if type_expr is not None:
        normalized_type = normalize_type_expr(type_expr.strip(), lineno)

    has_initializer = expr is not None
    if is_init:
        member_kind = f"init_{kind}"
    else:
        member_kind = kind

    public = True if is_init else is_pub
    rendered_expr = expr if expr is not None else "None"
    return (
        f"{CLASS_MEMBER_SENTINEL}({member_kind!r}, {name!r}, {normalized_type!r}, "
        f"{rendered_expr}, {has_initializer}, {public}, True)"
    )


def render_throws_decorator(throws_types: list[str]) -> str:
    rendered_args = ", ".join(repr(type_name) for type_name in throws_types)
    return f"@{THROWS_DECORATOR_SENTINEL}({rendered_args})"


def rewrite_catch_header(leading: str, lineno: int) -> str:
    body = leading.removeprefix("catch ").strip()
    if not body:
        raise SyntaxError(
            err(
                "E1028",
                lineno,
                "catch requires binding name",
                "Use `catch err { ... }` or `catch err: ErrorType { ... }`.",
            )
        )

    if ":" in body:
        name_text, type_text = body.split(":", 1)
        name = name_text.strip()
        error_type = type_text.strip()
        if not IDENTIFIER_RE.fullmatch(name) or not error_type:
            raise SyntaxError(
                err(
                    "E1028",
                    lineno,
                    "invalid typed catch syntax",
                    "Use `catch err: ErrorType { ... }`.",
                )
            )
        return f"except {error_type} as {name}:"

    name = body.strip()
    if not IDENTIFIER_RE.fullmatch(name):
        raise SyntaxError(
            err(
                "E1028",
                lineno,
                "invalid catch syntax",
                "Use `catch err { ... }` or `catch err: ErrorType { ... }`.",
            )
        )
    return f"except {RECOVERABLE_ERROR_BASE_NAME} as {name}:"
