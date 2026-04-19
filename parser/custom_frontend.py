from __future__ import annotations

import ast
import io
import re
import token
import tokenize
from dataclasses import dataclass


ENUM_SENTINEL = "__custom_enum_decl__"
BINDING_SENTINEL = "__custom_binding_decl__"
RECORD_LITERAL_SENTINEL = "__custom_record_literal__"
CLASS_MEMBER_SENTINEL = "__custom_class_member__"
CLASS_MARKER_SENTINEL = "__custom_class_marker__"
RECORD_MARKER_SENTINEL = "__custom_record_marker__"
PUB_DECORATOR_SENTINEL = "__custom_pub__"
SETUP_METHOD_NAME = "__tython_setup__"

_RESERVED_WORDS = {
    "const",
    "var",
    "pub",
    "record",
    "class",
    "setup",
    "init",
    "is",
    "this",
    "true",
    "false",
    "none",
    "int",
    "float",
    "bool",
    "str",
}

_ENUM_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)enum[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*:[ \t]*(?:#.*)?$"
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BINDING_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?(?P<kind>const|var)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:[ \t]*:[ \t]*(?P<type>[^=]+?))?[ \t]*=[ \t]*(?P<expr>.+)$"
)
_BINDING_NO_INIT_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?(?P<kind>const|var)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:[ \t]*:[ \t]*(?P<type>.+))?[ \t]*$"
)
_TYPE_BASE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CLASS_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?class[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:[ \t]+is[ \t]+(?P<record>[A-Za-z_][A-Za-z0-9_]*(?:[ \t]*,[ \t]*[A-Za-z_][A-Za-z0-9_]*)*))?[ \t]*$"
)
_RECORD_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:(?P<pub>pub)[ \t]+)?record[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
)
_CLASS_MEMBER_RE = re.compile(
    r"^(?:(?P<pub>pub)[ \t]+)?(?:(?P<init>init)[ \t]+)?(?P<kind>var|const)[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:[ \t]*:[ \t]*(?P<type>[^=]+?))?(?:[ \t]*=[ \t]*(?P<expr>.+))?$"
)
_RECORD_FIELD_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*:[ \t]*(?P<type>.+)$"
)


@dataclass(frozen=True)
class CustomFrontendOutput:
    source: str
    tree: ast.AST


@dataclass
class _BlockFrame:
    lineno: int
    has_statement: bool
    kind: str


def parse_custom_source(source: str) -> CustomFrontendOutput:
    rewritten = _rewrite_record_literal_blocks(source)
    rewritten = _rewrite_this_references(rewritten)
    rewritten = _rewrite_brace_and_functions(rewritten)
    rewritten = _rewrite_enum_blocks(rewritten)
    rewritten = _rewrite_bindings(rewritten)
    rewritten = _rewrite_ternary_expressions(rewritten)
    rewritten = _rewrite_named_call_args(rewritten)
    rewritten = _rewrite_lowercase_literals(rewritten)
    tree = ast.parse(rewritten, mode="exec")
    return CustomFrontendOutput(source=rewritten, tree=tree)


def _rewrite_brace_and_functions(source: str) -> str:
    lines = source.splitlines()
    output: list[str] = []
    level = 0
    stack: list[_BlockFrame] = []

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
                raise SyntaxError(_err("E1005", lineno, "unmatched '}'", "Remove extra closing brace."))
            closed = stack.pop()
            if not closed.has_statement:
                raise SyntaxError(
                    _err(
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
                _err(
                    "E1006",
                    lineno,
                    "`function` keyword is not supported",
                    "Use `func` for function declarations.",
                )
            )

        if "extends" in leading or re.search(r"\bsuper\b", leading):
            raise SyntaxError(
                _err(
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

        class_header = _CLASS_HEADER_RE.fullmatch(leading) if opens_block else None
        if class_header is not None:
            if stack:
                stack[-1].has_statement = True
            class_name = class_header.group("name")
            conformance = class_header.group("record")
            pub = class_header.group("pub") is not None
            output.append(("    " * level) + f"class {class_name}:")
            output.append(
                ("    " * (level + 1))
                + f'{CLASS_MARKER_SENTINEL}({conformance!r}, {pub})'
            )
            level += 1
            stack.append(_BlockFrame(lineno=lineno, has_statement=True, kind="class"))
            continue

        record_header = _RECORD_HEADER_RE.fullmatch(leading) if opens_block else None
        if record_header is not None:
            if stack:
                stack[-1].has_statement = True
            record_name = record_header.group("name")
            pub = record_header.group("pub") is not None
            output.append(("    " * level) + f"class {record_name}:")
            output.append(
                ("    " * (level + 1))
                + f"{RECORD_MARKER_SENTINEL}({pub})"
            )
            level += 1
            stack.append(_BlockFrame(lineno=lineno, has_statement=True, kind="record"))
            continue

        if current_kind == "record":
            field = _RECORD_FIELD_RE.fullmatch(leading)
            if field is None:
                raise SyntaxError(
                    _err(
                        "E1022",
                        lineno,
                        "invalid record member",
                        "Use `name: Type` fields only inside records.",
                    )
                )
            name = field.group("name")
            type_expr = _normalize_type_expr(field.group("type").strip(), lineno)
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
                    _err(
                        "E1023",
                        lineno,
                        "`setup` cannot be marked pub",
                        "Use bare `setup { ... }`.",
                    )
                )
            if leading.startswith("setup(") or leading.startswith("setup ->"):
                raise SyntaxError(
                    _err(
                        "E1024",
                        lineno,
                        "invalid setup declaration",
                        "Use `setup { ... }` with no parameters and no return annotation.",
                    )
                )

            if opens_block and leading == "setup":
                if stack:
                    stack[-1].has_statement = True
                output.append(("    " * level) + f"def {SETUP_METHOD_NAME}(self) -> None:")
                level += 1
                stack.append(_BlockFrame(lineno=lineno, has_statement=False, kind="setup"))
                continue

            member_line = _rewrite_class_member_line(leading, lineno)
            if member_line is not None:
                if stack:
                    stack[-1].has_statement = True
                output.append(("    " * level) + member_line)
                continue

        if leading.startswith("pub func "):
            if opens_block:
                def_header = _rewrite_func_block_decl(
                    leading.removeprefix("pub ").strip(),
                    lineno,
                    is_method=current_kind in {"class", "setup"},
                )
                if stack:
                    stack[-1].has_statement = True
                output.append(("    " * level) + f"@{PUB_DECORATOR_SENTINEL}")
                output.append(("    " * level) + def_header)
                level += 1
                stack.append(
                    _BlockFrame(
                        lineno=lineno,
                        has_statement=False,
                        kind="method" if current_kind == "class" else "block",
                    )
                )
                continue

            def_header, expr_body = _rewrite_func_expression_decl(
                leading.removeprefix("pub ").strip(),
                lineno,
                is_method=current_kind in {"class", "setup"},
            )
            if stack:
                stack[-1].has_statement = True
            output.append(("    " * level) + f"@{PUB_DECORATOR_SENTINEL}")
            output.append(("    " * level) + def_header)
            output.append(("    " * (level + 1)) + f"return {expr_body}")
            continue

        if leading.startswith("func ") and not opens_block:
            def_header, expr_body = _rewrite_func_expression_decl(
                leading,
                lineno,
                is_method=current_kind == "class",
            )
            if stack:
                stack[-1].has_statement = True
            output.append(("    " * level) + def_header)
            output.append(("    " * (level + 1)) + f"return {expr_body}")
            continue

        if leading.startswith("func ") and opens_block:
            def_header = _rewrite_func_block_decl(
                leading,
                lineno,
                is_method=current_kind == "class",
            )
            if stack:
                stack[-1].has_statement = True
            output.append(("    " * level) + def_header)
            level += 1
            stack.append(
                _BlockFrame(
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

        has_brace_syntax = "{" in stripped or "}" in stripped or stripped.startswith("func ")
        if level == 0 and not has_brace_syntax:
            output.append(line)
        else:
            output.append(("    " * level) + leading)

        if opens_block:
            level += 1
            stack.append(_BlockFrame(lineno=lineno, has_statement=False, kind="block"))

    if level != 0:
        raise SyntaxError(_err("E1007", len(lines) or 1, "unclosed '{' block", "Close every opened block with '}'."))

    return "\n".join(output) + "\n"


def _rewrite_class_member_line(leading: str, lineno: int) -> str | None:
    member = _CLASS_MEMBER_RE.fullmatch(leading)
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
            _err(
                "E1025",
                lineno,
                "init fields are already public and cannot use `pub`",
                "Use `init var ...` or `init const ...`.",
            )
        )

    normalized_type: str | None = None
    if type_expr is not None:
        normalized_type = _normalize_type_expr(type_expr.strip(), lineno)

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


def _rewrite_record_literal_blocks(source: str) -> str:
    lines = source.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped.endswith("{"):
            out.append(line)
            i += 1
            continue

        head = stripped[:-1].rstrip()
        if (
            head.startswith("if ")
            or head.startswith("else")
            or head.startswith("while ")
            or head.startswith("func ")
            or head.startswith("setup")
            or head.startswith("class ")
            or head.startswith("record ")
            or head.startswith("enum ")
            or head.startswith("pub class ")
            or head.startswith("pub record ")
            or head.startswith("pub func ")
        ):
            out.append(line)
            i += 1
            continue

        type_match = re.match(r"^(?P<prefix>.*?)(?P<type>[A-Z][A-Za-z0-9_]*)$", head)
        if type_match is None or not type_match.group("prefix").strip():
            out.append(line)
            i += 1
            continue

        prefix = type_match.group("prefix")
        type_name = type_match.group("type")
        fields: list[tuple[str, str]] = []
        i += 1
        closed = False
        while i < len(lines):
            inner = lines[i].strip()
            if inner == "":
                i += 1
                continue
            if inner == "}":
                closed = True
                break
            key, value = _split_once_top_level(inner, ":")
            if key is None or value is None:
                raise SyntaxError(
                    _err(
                        "E1026",
                        i + 1,
                        "invalid record literal field",
                        "Use `field: expression` entries inside record literals.",
                    )
                )
            field_name = key.strip()
            if not _IDENTIFIER_RE.fullmatch(field_name):
                raise SyntaxError(
                    _err(
                        "E1026",
                        i + 1,
                        f"invalid record literal field name '{field_name}'",
                        "Use valid identifier names for fields.",
                    )
                )
            fields.append((field_name, value.strip()))
            i += 1

        if not closed:
            raise SyntaxError(
                _err(
                    "E1027",
                    len(lines),
                    "unclosed record literal block",
                    "Close record literals with `}`.",
                )
            )

        rendered = ", ".join(f"({k!r}, {v})" for k, v in fields)
        indent = line[: len(line) - len(line.lstrip(" \t"))]
        out.append(
            f"{indent}{prefix}{RECORD_LITERAL_SENTINEL}({type_name!r}, [{rendered}])"
        )
        i += 1

    return "\n".join(out) + "\n"


def _rewrite_this_references(source: str) -> str:
    stream = io.StringIO(source)
    out_tokens: list[tokenize.TokenInfo] = []
    for tok in tokenize.generate_tokens(stream.readline):
        if tok.type == tokenize.NAME and tok.string == "this":
            tok = tokenize.TokenInfo(tok.type, "self", tok.start, tok.end, tok.line)
        out_tokens.append(tok)
    return tokenize.untokenize(out_tokens)


def _rewrite_func_block_decl(leading: str, lineno: int, is_method: bool = False) -> str:
    signature = leading.removeprefix("func ").strip()
    name, params, return_type = _parse_func_signature(signature, lineno)
    rendered_params = ", ".join(_render_param(param, lineno) for param in params)
    if is_method:
        rendered_params = f"self, {rendered_params}" if rendered_params else "self"
    rendered_return = _custom_type_to_python_annotation(return_type, lineno)
    return f"def {name}({rendered_params}) -> {rendered_return}:"


def _rewrite_func_expression_decl(
    leading: str, lineno: int, is_method: bool = False
) -> tuple[str, str]:
    signature_text, expr_body = _split_once_top_level(leading.removeprefix("func ").strip(), "=")
    if signature_text is None or expr_body is None:
        raise SyntaxError(
            _err(
                "E1008",
                lineno,
                "invalid expression-bodied function declaration",
                "Use `func name(params) -> Type = expression`.",
            )
        )
    name, params, return_type = _parse_func_signature(signature_text.strip(), lineno)
    rendered_params = ", ".join(_render_param(param, lineno) for param in params)
    if is_method:
        rendered_params = f"self, {rendered_params}" if rendered_params else "self"
    rendered_return = _custom_type_to_python_annotation(return_type, lineno)
    return f"def {name}({rendered_params}) -> {rendered_return}:", expr_body.strip()


def _parse_func_signature(
    signature: str, lineno: int
) -> tuple[str, list[tuple[str, str | None, str | None]], str]:
    i = 0
    while i < len(signature) and signature[i].isspace():
        i += 1

    name_start = i
    while i < len(signature) and (signature[i].isalnum() or signature[i] == "_"):
        i += 1

    name = signature[name_start:i]
    if not name or not _IDENTIFIER_RE.fullmatch(name):
        raise SyntaxError(
            _err(
                "E1009",
                lineno,
                "invalid function name in declaration",
                "Use `func name(...) -> Type`.",
            )
        )

    while i < len(signature) and signature[i].isspace():
        i += 1

    if i >= len(signature) or signature[i] != "(":
        raise SyntaxError(_err("E1010", lineno, "function parameters must be enclosed in ()", "Add `( ... )` after function name."))

    close_paren = _find_matching(signature, i, "(", ")")
    params_text = signature[i + 1 : close_paren]
    rest = signature[close_paren + 1 :].strip()

    if not rest.startswith("->"):
        raise SyntaxError(
            _err(
                "E1011",
                lineno,
                "function return type is required",
                "Add `-> Type` in function declaration.",
            )
        )

    return_type = rest[2:].strip()
    if not return_type:
        raise SyntaxError(
            _err(
                "E1012",
                lineno,
                "function return type is missing",
                "Specify a return type after `->`.",
            )
        )

    params: list[tuple[str, str | None, str | None]] = []
    for raw_param in _split_top_level(params_text, ","):
        token_text = raw_param.strip()
        if not token_text:
            continue

        left, default = _split_once_top_level(token_text, "=")
        param_core = left.strip() if left is not None else token_text
        default_expr = default.strip() if default is not None else None

        name_and_type = _split_once_top_level(param_core, ":")
        if name_and_type[0] is None or name_and_type[1] is None:
            params.append((param_core.strip(), None, default_expr))
            continue

        param_name = name_and_type[0].strip()
        param_type = name_and_type[1].strip()
        params.append((param_name, param_type, default_expr))

    return name, params, return_type


def _render_param(param: tuple[str, str | None, str | None], lineno: int) -> str:
    name, type_expr, default_expr = param
    rendered = name
    if type_expr is not None:
        rendered_type = _custom_type_to_python_annotation(type_expr, lineno)
        rendered = f"{name}: {rendered_type}"
    if default_expr is not None:
        rendered += f" = {default_expr}"
    return rendered


def _custom_type_to_python_annotation(type_expr: str, lineno: int) -> str:
    normalized = _normalize_type_expr(type_expr, lineno)
    return _normalized_type_to_python_annotation(normalized)


def _normalized_type_to_python_annotation(normalized: str) -> str:
    if _is_function_type(normalized):
        return repr(normalized)

    if normalized.endswith("[]"):
        inner = _normalized_type_to_python_annotation(normalized[:-2])
        return f"list[{inner}]"

    if normalized == "none":
        return "None"
    return normalized


def _is_function_type(text: str) -> bool:
    return text.startswith("(") and ")->" in text


def _rewrite_enum_blocks(source: str) -> str:
    lines = source.splitlines(keepends=True)
    output: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        header = _ENUM_HEADER_RE.match(line.rstrip("\r\n"))
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
            if not _IDENTIFIER_RE.fullmatch(member_name):
                raise SyntaxError(
                    _err(
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
                _err(
                    "E1014",
                    i + 1,
                    f"enum {enum_name} must declare at least one member",
                    "Add one or more enum members.",
                )
            )

        list_literal = ", ".join(repr(member) for member in members)
        output.append(f'{indent}{ENUM_SENTINEL}("{enum_name}", [{list_literal}])\n')

    return "".join(output)


def _rewrite_bindings(source: str) -> str:
    output: list[str] = []

    for lineno, line in enumerate(source.splitlines(), start=1):
        binding = _BINDING_RE.match(line)
        if binding is not None:
            indent = binding.group("indent")
            kind = binding.group("kind")
            name = binding.group("name")
            type_expr = binding.group("type")
            expr = binding.group("expr")
            is_pub = binding.group("pub") is not None

            normalized_type = None
            if type_expr is not None:
                normalized_type = _normalize_type_expr(type_expr.strip(), lineno)

            output.append(
                f"{indent}{BINDING_SENTINEL}({kind!r}, {name!r}, {normalized_type!r}, {expr}, True, {is_pub})"
            )
            continue

        maybe_binding = _BINDING_NO_INIT_RE.match(line)
        if maybe_binding is not None:
            type_expr = maybe_binding.group("type")
            is_pub = maybe_binding.group("pub") is not None
            if type_expr is None:
                raise SyntaxError(
                    _err(
                        "E1001",
                        lineno,
                        f"{maybe_binding.group('kind')} binding '{maybe_binding.group('name')}' requires a type annotation when no initializer is provided",
                        "Use `name: Type` for empty declarations or provide `= value`.",
                    )
                )
            normalized_type = _normalize_type_expr(type_expr.strip(), lineno)
            output.append(
                f"{maybe_binding.group('indent')}{BINDING_SENTINEL}({maybe_binding.group('kind')!r}, {maybe_binding.group('name')!r}, {normalized_type!r}, None, False, {is_pub})"
            )
            continue

        output.append(line)

    return "\n".join(output) + "\n"


def _rewrite_ternary_expressions(source: str) -> str:
    lines = source.splitlines()
    out_lines: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        out_lines.append(_rewrite_ternary_in_line(line, lineno))
    return "\n".join(out_lines) + "\n"


def _rewrite_ternary_in_line(line: str, lineno: int) -> str:
    if "if" not in line or ":" not in line or "else" not in line:
        return line

    i = 0
    out: list[str] = []
    while i < len(line):
        if not _is_word_at(line, i, "if"):
            out.append(line[i])
            i += 1
            continue

        if _is_statement_if_position(line, i):
            out.append("if")
            i += 2
            continue

        prev = _previous_non_space(line, i)
        if prev is not None and prev in "+-*/%<>=!&|^":
            raise SyntaxError(
                _err(
                    "E1018",
                    lineno,
                    "ternary used as operator subexpression must be parenthesized",
                    "Wrap ternary with parentheses when embedding in operator expressions.",
                )
            )

        replacement, next_i = _parse_prefix_ternary(line, i, lineno)
        out.append(replacement)
        i = next_i

    return "".join(out)


def _parse_prefix_ternary(text: str, start: int, lineno: int) -> tuple[str, int]:
    cond_start = start + 2
    while cond_start < len(text) and text[cond_start].isspace():
        cond_start += 1

    cond_end = _find_top_level_colon(text, cond_start)
    if cond_end is None:
        raise SyntaxError(
            _err(
                "E1017",
                lineno,
                "invalid ternary syntax",
                "Use `if cond: expr else expr`.",
            )
        )

    true_start = cond_end + 1
    while true_start < len(text) and text[true_start].isspace():
        true_start += 1

    else_start = _find_top_level_else(text, true_start)
    if else_start is None:
        raise SyntaxError(
            _err(
                "E1017",
                lineno,
                "invalid ternary syntax",
                "Use `if cond: expr else expr`.",
            )
        )

    false_start = else_start + 4
    while false_start < len(text) and text[false_start].isspace():
        false_start += 1

    false_end = _find_ternary_false_end(text, false_start)

    cond = text[cond_start:cond_end].strip()
    true_expr = text[true_start:else_start].strip()
    false_expr = text[false_start:false_end].strip()
    if not cond or not true_expr or not false_expr:
        raise SyntaxError(
            _err(
                "E1017",
                lineno,
                "invalid ternary syntax",
                "Use `if cond: expr else expr`.",
            )
        )

    return f"({true_expr} if {cond} else {false_expr})", false_end


def _find_top_level_colon(text: str, start: int) -> int | None:
    paren = 0
    square = 0
    brace = 0
    quote: str | None = None
    escape = False
    i = start
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            square += 1
        elif ch == "]":
            square = max(0, square - 1)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        elif ch == ":" and paren == 0 and square == 0 and brace == 0:
            return i
        i += 1
    return None


def _find_top_level_else(text: str, start: int) -> int | None:
    paren = 0
    square = 0
    brace = 0
    quote: str | None = None
    escape = False
    i = start
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            square += 1
        elif ch == "]":
            square = max(0, square - 1)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        elif paren == 0 and square == 0 and brace == 0 and _is_word_at(text, i, "else"):
            return i
        i += 1
    return None


def _find_ternary_false_end(text: str, start: int) -> int:
    paren = 0
    square = 0
    brace = 0
    quote: str | None = None
    escape = False
    i = start
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            if paren == 0:
                return i
            paren -= 1
        elif ch == "[":
            square += 1
        elif ch == "]":
            if square == 0:
                return i
            square -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            if brace == 0:
                return i
            brace -= 1
        elif ch == "," and paren == 0 and square == 0 and brace == 0:
            return i
        i += 1
    return len(text)


def _is_statement_if_position(text: str, if_index: int) -> bool:
    prefix = text[:if_index]
    if prefix.strip() == "":
        return _find_top_level_else(text, if_index + 2) is None
    if prefix.rstrip().endswith("else "):
        return True
    return False


def _is_word_at(text: str, index: int, word: str) -> bool:
    end = index + len(word)
    if end > len(text):
        return False
    if text[index:end] != word:
        return False
    left_ok = index == 0 or (not text[index - 1].isalnum() and text[index - 1] != "_")
    right_ok = end == len(text) or (not text[end].isalnum() and text[end] != "_")
    return left_ok and right_ok


def _previous_non_space(text: str, index: int) -> str | None:
    i = index - 1
    while i >= 0:
        if not text[i].isspace():
            return text[i]
        i -= 1
    return None


def _rewrite_named_call_args(source: str) -> str:
    stream = io.StringIO(source)
    tokens = list(tokenize.generate_tokens(stream.readline))
    out_tokens: list[tokenize.TokenInfo] = []

    paren_stack: list[str] = []
    square_depth = 0
    brace_depth = 0

    last_sig: tokenize.TokenInfo | None = None
    second_last_sig: tokenize.TokenInfo | None = None

    for tok in tokens:
        token_type = tok.type
        token_str = tok.string

        if token_type == token.OP and token_str == "(":
            kind = "other"
            if (
                last_sig is not None
                and second_last_sig is not None
                and second_last_sig.type == token.NAME
                and second_last_sig.string == "def"
                and last_sig.type == token.NAME
            ):
                kind = "def_params"
            elif last_sig is not None and _is_call_paren_after(last_sig):
                kind = "call"
            paren_stack.append(kind)

        elif token_type == token.OP and token_str == ")":
            if paren_stack:
                paren_stack.pop()

        elif token_type == token.OP and token_str == "[":
            square_depth += 1
        elif token_type == token.OP and token_str == "]":
            square_depth = max(0, square_depth - 1)
        elif token_type == token.OP and token_str == "{":
            brace_depth += 1
        elif token_type == token.OP and token_str == "}":
            brace_depth = max(0, brace_depth - 1)

        if (
            token_type == token.OP
            and token_str == ":"
            and paren_stack
            and paren_stack[-1] == "call"
            and square_depth == 0
            and brace_depth == 0
        ):
            tok = tokenize.TokenInfo(tok.type, "=", tok.start, tok.end, tok.line)

        out_tokens.append(tok)

        if token_type not in {
            token.INDENT,
            token.DEDENT,
            token.NEWLINE,
            token.NL,
            token.ENDMARKER,
            token.COMMENT,
        }:
            second_last_sig = last_sig
            last_sig = tok

    return tokenize.untokenize(out_tokens)


def _is_call_paren_after(tok: tokenize.TokenInfo) -> bool:
    if tok.type in {token.NAME, token.NUMBER, token.STRING}:
        return True
    if tok.type == token.OP and tok.string in {")", "]"}:
        return True
    return False


def _rewrite_lowercase_literals(source: str) -> str:
    stream = io.StringIO(source)
    out_tokens: list[tokenize.TokenInfo] = []

    for tok in tokenize.generate_tokens(stream.readline):
        if tok.type == tokenize.NAME:
            if tok.string == "true":
                tok = tokenize.TokenInfo(tok.type, "True", tok.start, tok.end, tok.line)
            elif tok.string == "false":
                tok = tokenize.TokenInfo(tok.type, "False", tok.start, tok.end, tok.line)
            elif tok.string == "none":
                tok = tokenize.TokenInfo(tok.type, "None", tok.start, tok.end, tok.line)
        out_tokens.append(tok)

    return tokenize.untokenize(out_tokens)


def _normalize_type_expr(type_expr: str, lineno: int) -> str:
    if not type_expr:
        raise SyntaxError(
            _err("E1002", lineno, "empty type annotation", "Provide a concrete type name.")
        )

    parser = _TypeParser(type_expr, lineno)
    normalized = parser.parse_type()
    parser.skip_ws()
    if not parser.at_end():
        raise SyntaxError(
            _err(
                "E1003",
                lineno,
                f"invalid type annotation '{type_expr}'",
                "Unexpected trailing tokens in type expression.",
            )
        )
    return normalized


class _TypeParser:
    def __init__(self, text: str, lineno: int) -> None:
        self.text = text
        self.lineno = lineno
        self.i = 0

    def at_end(self) -> bool:
        return self.i >= len(self.text)

    def skip_ws(self) -> None:
        while not self.at_end() and self.text[self.i].isspace():
            self.i += 1

    def peek(self) -> str | None:
        if self.at_end():
            return None
        return self.text[self.i]

    def parse_type(self) -> str:
        self.skip_ws()
        if self.peek() == "(":
            return self._parse_function_type_or_group()
        return self._parse_base_or_list()

    def _parse_function_type_or_group(self) -> str:
        start = self.i
        close = _find_matching(self.text, self.i, "(", ")")
        self.i = close + 1
        self.skip_ws()
        if self.text[self.i : self.i + 2] != "->":
            raise SyntaxError(
                _err(
                    "E1003",
                    self.lineno,
                    f"invalid type annotation '{self.text}'",
                    "Function types must use `(name: Type, ...) -> ReturnType`.",
                )
            )
        self.i += 2

        params_text = self.text[start + 1 : close]
        params: list[str] = []
        for raw in _split_top_level(params_text, ","):
            token_text = raw.strip()
            if not token_text:
                continue
            left, right = _split_once_top_level(token_text, ":")
            if left is None or right is None:
                raise SyntaxError(
                    _err(
                        "E1003",
                        self.lineno,
                        f"invalid function type parameter '{token_text}'",
                        "Use parameter form `name: Type` inside function types.",
                    )
                )
            param_name = left.strip()
            if not _IDENTIFIER_RE.fullmatch(param_name):
                raise SyntaxError(
                    _err(
                        "E1003",
                        self.lineno,
                        f"invalid function type parameter name '{param_name}'",
                        "Use a valid identifier name.",
                    )
                )
            child = _TypeParser(right.strip(), self.lineno)
            param_type = child.parse_type()
            child.skip_ws()
            if not child.at_end():
                raise SyntaxError(
                    _err(
                        "E1003",
                        self.lineno,
                        f"invalid function type parameter '{token_text}'",
                        "Unexpected trailing tokens in parameter type.",
                    )
                )
            params.append(f"{param_name}:{param_type}")

        return_type = self.parse_type()
        normalized = f"({','.join(params)})->{return_type}"

        while True:
            self.skip_ws()
            if self.text[self.i : self.i + 2] != "[]":
                break
            normalized += "[]"
            self.i += 2
        return normalized

    def _parse_base_or_list(self) -> str:
        self.skip_ws()
        start = self.i
        while not self.at_end() and (self.text[self.i].isalnum() or self.text[self.i] == "_"):
            self.i += 1
        base = self.text[start:self.i]

        if not base or not _TYPE_BASE_RE.fullmatch(base):
            raise SyntaxError(
                _err(
                    "E1003",
                    self.lineno,
                    f"invalid type annotation '{self.text}'",
                    "Use names like int, str, MyType, or function types.",
                )
            )

        if base in _RESERVED_WORDS and base not in {"int", "float", "bool", "str", "none"}:
            raise SyntaxError(
                _err(
                    "E1004",
                    self.lineno,
                    f"invalid type annotation '{self.text}'",
                    "Reserved keywords cannot be used as type names.",
                )
            )

        normalized = base
        while True:
            self.skip_ws()
            if self.text[self.i : self.i + 2] != "[]":
                break
            normalized += "[]"
            self.i += 2
        return normalized


def _split_top_level(text: str, delimiter: str) -> list[str]:
    result: list[str] = []
    start = 0
    paren = 0
    square = 0
    brace = 0

    for idx, ch in enumerate(text):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            square += 1
        elif ch == "]":
            square -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == delimiter and paren == 0 and square == 0 and brace == 0:
            result.append(text[start:idx])
            start = idx + 1

    result.append(text[start:])
    return result


def _split_once_top_level(text: str, delimiter: str) -> tuple[str | None, str | None]:
    paren = 0
    square = 0
    brace = 0

    for idx, ch in enumerate(text):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            square += 1
        elif ch == "]":
            square -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == delimiter and paren == 0 and square == 0 and brace == 0:
            return text[:idx], text[idx + 1 :]
    return None, None


def _find_matching(text: str, start: int, opener: str, closer: str) -> int:
    depth = 0
    for idx in range(start, len(text)):
        if text[idx] == opener:
            depth += 1
        elif text[idx] == closer:
            depth -= 1
            if depth == 0:
                return idx
    raise SyntaxError(
        _err(
            "E1015",
            1,
            f"unmatched '{opener}'",
            f"Ensure every `{opener}` has a matching `{closer}`.",
        )
    )


def _err(code: str, lineno: int, message: str, hint: str) -> str:
    return f"[{code}] Line {lineno}: {message}. Hint: {hint}"
