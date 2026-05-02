from __future__ import annotations

import re

from .constants import (
    BINDING_NO_INIT_RE,
    BINDING_RE,
    BINDING_SENTINEL,
    ENUM_HEADER_RE,
    ENUM_SENTINEL,
    FILE_IMPORT_SENTINEL,
    IDENTIFIER_RE,
    NATIVE_IMPORT_SENTINEL,
    PYIMPORT_SENTINEL,
    TRY_PROPAGATE_SENTINEL,
)
from .errors import err
from .type_system import normalize_type_expr
from .rewriters_ternary import rewrite_ternary_in_line


_PYIMPORT_RE = re.compile(
    r"^(?P<indent>[ \t]*)pyimport[ \t]+(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?[ \t]*$"
)
_FILE_IMPORT_RE = re.compile(
    r"^(?P<indent>[ \t]*)import[ \t]+(?P<quote>['\"])(?P<path>.+?)(?P=quote)[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
)
_NATIVE_IMPORT_RE = re.compile(
    r"^(?P<indent>[ \t]*)import[ \t]+(?P<target>[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)+)[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
)


def rewrite_postbrace_combined(source: str) -> str:
    """Single pass over lines after brace/function rewriting.

    Preserves original pipeline behavior while avoiding multiple full-source scans:
      - strict import forms
      - enum blocks
      - const/var bindings
      - prefix ternary
      - try-propagation
    """
    lines = source.splitlines()
    out_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        header = ENUM_HEADER_RE.match(line)
        if header is not None:
            indent = header.group("indent")
            enum_name = header.group("name")
            members: list[str] = []
            i += 1

            while i < len(lines):
                current = lines[i]
                stripped = current.strip()
                current_indent = current[: len(current) - len(current.lstrip(" \t"))]

                if stripped == "":
                    i += 1
                    continue

                if len(current_indent) <= len(indent):
                    break

                member_name = stripped.split("#", 1)[0].strip()
                if not IDENTIFIER_RE.fullmatch(member_name):
                    raise SyntaxError(
                        err(
                            "E1013",
                            i + 1,
                            f"invalid enum member {member_name!r} in enum {enum_name}",
                            "Enum members must be valid identifiers.",
                        )
                    )
                members.append(member_name)
                i += 1

            if not members:
                raise SyntaxError(
                    err(
                        "E1014",
                        i + 1,
                        f"enum {enum_name} must declare at least one member",
                        "Add one or more enum members.",
                    )
                )

            list_literal = ", ".join(repr(member) for member in members)
            out_lines.append(f'{indent}{ENUM_SENTINEL}("{enum_name}", [{list_literal}])')
            continue

        lineno = i + 1
        line = _rewrite_import_forms_in_line(line, lineno)
        line = _rewrite_binding_in_line(line, lineno)
        line = rewrite_ternary_in_line(line, lineno)
        line = _rewrite_try_in_line(line)
        out_lines.append(line)
        i += 1

    return "\n".join(out_lines) + "\n"


def _rewrite_import_forms_in_line(line: str, lineno: int) -> str:
    code, sep, comment = line.partition("#")
    stripped = code.strip()
    if stripped == "":
        return line

    py_match = _PYIMPORT_RE.match(code)
    if py_match is not None:
        indent = py_match.group("indent")
        module = py_match.group("module")
        alias = py_match.group("alias")
        rendered = f"{indent}{PYIMPORT_SENTINEL}({module!r}, {alias!r})"
        if sep:
            rendered += f"  #{comment}"
        return rendered

    file_match = _FILE_IMPORT_RE.match(code)
    if file_match is not None:
        indent = file_match.group("indent")
        path = file_match.group("path")
        alias = file_match.group("alias")
        rendered = f"{indent}{FILE_IMPORT_SENTINEL}({path!r}, {alias!r})"
        if sep:
            rendered += f"  #{comment}"
        return rendered

    native_match = _NATIVE_IMPORT_RE.match(code)
    if native_match is not None:
        indent = native_match.group("indent")
        target = native_match.group("target")
        alias = native_match.group("alias")
        rendered = f"{indent}{NATIVE_IMPORT_SENTINEL}({target!r}, {alias!r})"
        if sep:
            rendered += f"  #{comment}"
        return rendered

    if stripped.startswith("import ") or stripped.startswith("pyimport "):
        raise SyntaxError(
            err(
                "E1028",
                lineno,
                "invalid import form",
                'Use one of: `import pkg/mod as alias`, `import "./file.ty" as alias`, `pyimport module [as alias]`.',
            )
        )

    return line


def _rewrite_binding_in_line(line: str, lineno: int) -> str:
    binding = BINDING_RE.match(line)
    if binding is not None:
        indent = binding.group("indent")
        kind = binding.group("kind")
        name = binding.group("name")
        type_expr = binding.group("type")
        expr = binding.group("expr")
        is_pub = binding.group("pub") is not None

        normalized_type = None
        if type_expr is not None:
            normalized_type = normalize_type_expr(type_expr.strip(), lineno)

        return (
            f"{indent}{BINDING_SENTINEL}({kind!r}, {name!r}, {normalized_type!r}, {expr}, True, {is_pub})"
        )

    maybe_binding = BINDING_NO_INIT_RE.match(line)
    if maybe_binding is not None:
        type_expr = maybe_binding.group("type")
        is_pub = maybe_binding.group("pub") is not None
        if type_expr is None:
            raise SyntaxError(
                err(
                    "E1001",
                    lineno,
                    f"{maybe_binding.group('kind')} binding '{maybe_binding.group('name')}' requires a type annotation when no initializer is provided",
                    "Use `name: Type` for empty declarations or provide `= value`.",
                )
            )
        normalized_type = normalize_type_expr(type_expr.strip(), lineno)
        return (
            f"{maybe_binding.group('indent')}{BINDING_SENTINEL}({maybe_binding.group('kind')!r}, {maybe_binding.group('name')!r}, {normalized_type!r}, None, False, {is_pub})"
        )

    return line


def _rewrite_try_in_line(line: str) -> str:
    i = 0
    out: list[str] = []
    while i < len(line):
        if not _is_word_at(line, i, "try"):
            out.append(line[i])
            i += 1
            continue

        j = i + 3
        while j < len(line) and line[j].isspace():
            j += 1
        if j < len(line) and line[j] == ":":
            out.append("try")
            i += 3
            continue

        expr_start = j
        while j < len(line) and (line[j].isalnum() or line[j] in {"_", "."}):
            j += 1
        if j == expr_start:
            out.append(line[i])
            i += 1
            continue
        while j < len(line) and line[j].isspace():
            j += 1
        if j >= len(line) or line[j] != "(":
            out.append(line[i])
            i += 1
            continue

        close = _find_matching_paren(line, j)
        if close is None:
            out.append(line[i])
            i += 1
            continue

        call_expr = line[expr_start : close + 1]
        out.append(f"{TRY_PROPAGATE_SENTINEL}({call_expr})")
        i = close + 1

    return "".join(out)


def _is_word_at(text: str, index: int, word: str) -> bool:
    end = index + len(word)
    if end > len(text):
        return False
    if text[index:end] != word:
        return False
    left_ok = index == 0 or (not text[index - 1].isalnum() and text[index - 1] != "_")
    right_ok = end == len(text) or (not text[end].isalnum() and text[end] != "_")
    return left_ok and right_ok


def _find_matching_paren(text: str, start: int) -> int | None:
    depth = 0
    quote: str | None = None
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if quote is not None:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue

        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                return idx
    return None

