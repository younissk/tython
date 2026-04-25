from __future__ import annotations

from .constants import (
    BINDING_NO_INIT_RE,
    BINDING_RE,
    BINDING_SENTINEL,
    ENUM_HEADER_RE,
    ENUM_SENTINEL,
    IDENTIFIER_RE,
)
from .errors import err
from .type_system import normalize_type_expr


def rewrite_enum_blocks(source: str) -> str:
    lines = source.splitlines(keepends=True)
    output: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        header = ENUM_HEADER_RE.match(line.rstrip("\r\n"))
        if header is None:
            output.append(line)
            i += 1
            continue

        indent = header.group("indent")
        enum_name = header.group("name")
        members: list[str] = []
        i += 1

        while i < len(lines):
            current = lines[i]
            stripped = current.strip()
            current_no_nl = current.rstrip("\r\n")
            current_indent = current_no_nl[
                : len(current_no_nl) - len(current_no_nl.lstrip(" \t"))
            ]

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
        output.append(f'{indent}{ENUM_SENTINEL}("{enum_name}", [{list_literal}])\n')

    return "".join(output)


def rewrite_bindings(source: str) -> str:
    output: list[str] = []

    for lineno, line in enumerate(source.splitlines(), start=1):
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

            output.append(
                f"{indent}{BINDING_SENTINEL}({kind!r}, {name!r}, {normalized_type!r}, {expr}, True, {is_pub})"
            )
            continue

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
            output.append(
                f"{maybe_binding.group('indent')}{BINDING_SENTINEL}({maybe_binding.group('kind')!r}, {maybe_binding.group('name')!r}, {normalized_type!r}, None, False, {is_pub})"
            )
            continue

        output.append(line)

    return "\n".join(output) + "\n"
