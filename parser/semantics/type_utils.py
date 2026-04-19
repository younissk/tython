from __future__ import annotations

import ast

from .errors import err
from .models import FunctionSignature


def annotation_to_custom_type(annotation: ast.expr | None) -> str:
    if annotation is None:
        raise SyntaxError(err("E2034", 1, "annotation is required"))

    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return "none"

    if isinstance(annotation, ast.Name):
        if annotation.id == "None":
            return "none"
        return annotation.id

    if isinstance(annotation, ast.Subscript):
        if isinstance(annotation.slice, ast.Slice):
            raise SyntaxError(
                err(
                    "E2035",
                    getattr(annotation, "lineno", 1),
                    "slice syntax is not allowed in type annotations",
                    "Use list[T] in Python AST or T[] in Tython syntax.",
                )
            )
        if not isinstance(annotation.value, ast.Name) or annotation.value.id != "list":
            raise SyntaxError(
                err(
                    "E2035",
                    getattr(annotation, "lineno", 1),
                    "only list[...] annotations are supported",
                    "Use list[T] in Python AST or T[] in Tython syntax.",
                )
            )
        return f"{annotation_to_custom_type(annotation.slice)}[]"

    raise SyntaxError(
        err(
            "E2036",
            getattr(annotation, "lineno", 1),
            "invalid annotation",
            "Use a type name like int or list[int].",
        )
    )


def extract_int_literal(expr: ast.expr) -> int | None:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, int):
        return expr.value
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub):
        if isinstance(expr.operand, ast.Constant) and isinstance(expr.operand.value, int):
            return -expr.operand.value
    return None


def iter_type_atoms(type_name: str, lineno: int) -> list[str]:
    if is_function_type(type_name):
        params_text, return_text = split_function_type(type_name, lineno)
        atoms: list[str] = []
        for raw in split_top_level(params_text, ","):
            token_text = raw.strip()
            if not token_text:
                continue
            name, param_type = split_once_top_level(token_text, ":")
            if name is None or param_type is None:
                raise SyntaxError(
                    err(
                        "E2081",
                        lineno,
                        f"invalid function type parameter '{token_text}'",
                        "Use `name: Type` in function type parameters.",
                    )
                )
            atoms.extend(iter_type_atoms(param_type.strip(), lineno))
        atoms.extend(iter_type_atoms(return_text.strip(), lineno))
        return atoms

    if type_name.endswith("[]"):
        return iter_type_atoms(type_name[:-2], lineno)
    return [type_name]


def is_function_type(type_name: str) -> bool:
    return type_name.startswith("(") and ")->" in type_name


def split_function_type(type_name: str, lineno: int) -> tuple[str, str]:
    close = find_matching(type_name, 0, "(", ")", lineno)
    if type_name[close + 1 : close + 3] != "->":
        raise SyntaxError(
            err(
                "E2082",
                lineno,
                f"invalid function type '{type_name}'",
                "Use `(name: Type, ...) -> ReturnType`.",
            )
        )
    return type_name[1:close], type_name[close + 3 :]


def function_type_matches_signature(
    required_type: str, signature: FunctionSignature, lineno: int
) -> bool:
    if not is_function_type(required_type):
        return False
    params_text, return_text = split_function_type(required_type, lineno)
    expected_param_types: list[str] = []
    for raw in split_top_level(params_text, ","):
        token_text = raw.strip()
        if not token_text:
            continue
        left, right = split_once_top_level(token_text, ":")
        if left is None or right is None:
            return False
        expected_param_types.append(right.strip())

    if len(expected_param_types) != len(signature.params):
        return False
    for expected, actual in zip(expected_param_types, signature.params):
        if expected != actual.type_name:
            return False
    return return_text.strip() == signature.return_type


def signature_to_function_type(signature: FunctionSignature) -> str:
    params = ",".join(f"{param.name}:{param.type_name}" for param in signature.params)
    return f"({params})->{signature.return_type}"


def split_top_level(text: str, delimiter: str) -> list[str]:
    result: list[str] = []
    start = 0
    paren = 0
    square = 0

    for idx, ch in enumerate(text):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            square += 1
        elif ch == "]":
            square -= 1
        elif ch == delimiter and paren == 0 and square == 0:
            result.append(text[start:idx])
            start = idx + 1

    result.append(text[start:])
    return result


def split_once_top_level(text: str, delimiter: str) -> tuple[str | None, str | None]:
    paren = 0
    square = 0

    for idx, ch in enumerate(text):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            square += 1
        elif ch == "]":
            square -= 1
        elif ch == delimiter and paren == 0 and square == 0:
            return text[:idx], text[idx + 1 :]

    return None, None


def find_matching(text: str, start: int, opener: str, closer: str, lineno: int) -> int:
    depth = 0
    for idx in range(start, len(text)):
        if text[idx] == opener:
            depth += 1
        elif text[idx] == closer:
            depth -= 1
            if depth == 0:
                return idx
    raise SyntaxError(
        err(
            "E2083",
            lineno,
            f"unmatched '{opener}' in type expression",
            f"Ensure `{opener}` is closed by `{closer}`.",
        )
    )
