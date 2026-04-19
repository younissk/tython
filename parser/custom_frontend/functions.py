from __future__ import annotations

from .constants import IDENTIFIER_RE
from .errors import err
from .helpers import find_matching, split_once_top_level, split_top_level
from .type_system import custom_type_to_python_annotation


def rewrite_func_block_decl(leading: str, lineno: int, is_method: bool = False) -> str:
    signature = leading.removeprefix("func ").strip()
    name, params, return_type = parse_func_signature(signature, lineno)
    rendered_params = ", ".join(render_param(param, lineno) for param in params)
    if is_method:
        rendered_params = f"self, {rendered_params}" if rendered_params else "self"
    rendered_return = custom_type_to_python_annotation(return_type, lineno)
    return f"def {name}({rendered_params}) -> {rendered_return}:"


def rewrite_func_expression_decl(
    leading: str, lineno: int, is_method: bool = False
) -> tuple[str, str]:
    signature_text, expr_body = split_once_top_level(leading.removeprefix("func ").strip(), "=")
    if signature_text is None or expr_body is None:
        raise SyntaxError(
            err(
                "E1008",
                lineno,
                "invalid expression-bodied function declaration",
                "Use `func name(params) -> Type = expression`.",
            )
        )
    name, params, return_type = parse_func_signature(signature_text.strip(), lineno)
    rendered_params = ", ".join(render_param(param, lineno) for param in params)
    if is_method:
        rendered_params = f"self, {rendered_params}" if rendered_params else "self"
    rendered_return = custom_type_to_python_annotation(return_type, lineno)
    return f"def {name}({rendered_params}) -> {rendered_return}:", expr_body.strip()


def parse_func_signature(
    signature: str, lineno: int
) -> tuple[str, list[tuple[str, str | None, str | None]], str]:
    i = 0
    while i < len(signature) and signature[i].isspace():
        i += 1

    name_start = i
    while i < len(signature) and (signature[i].isalnum() or signature[i] == "_"):
        i += 1

    name = signature[name_start:i]
    if not name or not IDENTIFIER_RE.fullmatch(name):
        raise SyntaxError(
            err(
                "E1009",
                lineno,
                "invalid function name in declaration",
                "Use `func name(...) -> Type`.",
            )
        )

    while i < len(signature) and signature[i].isspace():
        i += 1

    if i >= len(signature) or signature[i] != "(":
        raise SyntaxError(
            err(
                "E1010",
                lineno,
                "function parameters must be enclosed in ()",
                "Add `( ... )` after function name.",
            )
        )

    close_paren = find_matching(signature, i, "(", ")")
    params_text = signature[i + 1 : close_paren]
    rest = signature[close_paren + 1 :].strip()

    if not rest.startswith("->"):
        raise SyntaxError(
            err(
                "E1011",
                lineno,
                "function return type is required",
                "Add `-> Type` in function declaration.",
            )
        )

    return_type = rest[2:].strip()
    if not return_type:
        raise SyntaxError(
            err(
                "E1012",
                lineno,
                "function return type is missing",
                "Specify a return type after `->`.",
            )
        )

    params: list[tuple[str, str | None, str | None]] = []
    for raw_param in split_top_level(params_text, ","):
        token_text = raw_param.strip()
        if not token_text:
            continue

        left, default = split_once_top_level(token_text, "=")
        param_core = left.strip() if left is not None else token_text
        default_expr = default.strip() if default is not None else None

        name_and_type = split_once_top_level(param_core, ":")
        if name_and_type[0] is None or name_and_type[1] is None:
            params.append((param_core.strip(), None, default_expr))
            continue

        param_name = name_and_type[0].strip()
        param_type = name_and_type[1].strip()
        params.append((param_name, param_type, default_expr))

    return name, params, return_type


def render_param(param: tuple[str, str | None, str | None], lineno: int) -> str:
    name, type_expr, default_expr = param
    rendered = name
    if type_expr is not None:
        rendered_type = custom_type_to_python_annotation(type_expr, lineno)
        rendered = f"{name}: {rendered_type}"
    if default_expr is not None:
        rendered += f" = {default_expr}"
    return rendered
