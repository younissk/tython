from __future__ import annotations

from .constants import IDENTIFIER_RE, RESERVED_WORDS, TYPE_BASE_RE
from .errors import err
from .helpers import find_matching, split_once_top_level, split_top_level


def normalize_type_expr(type_expr: str, lineno: int) -> str:
    if not type_expr:
        raise SyntaxError(
            err("E1002", lineno, "empty type annotation", "Provide a concrete type name.")
        )

    parser = _TypeParser(type_expr, lineno)
    normalized = parser.parse_type()
    parser.skip_ws()
    if not parser.at_end():
        raise SyntaxError(
            err(
                "E1003",
                lineno,
                f"invalid type annotation '{type_expr}'",
                "Unexpected trailing tokens in type expression.",
            )
        )
    return normalized


def custom_type_to_python_annotation(type_expr: str, lineno: int) -> str:
    normalized = normalize_type_expr(type_expr, lineno)
    return normalized_type_to_python_annotation(normalized)


def normalized_type_to_python_annotation(normalized: str) -> str:
    if is_function_type(normalized):
        return repr(normalized)

    if normalized.endswith("[]"):
        inner = normalized_type_to_python_annotation(normalized[:-2])
        return f"list[{inner}]"

    if normalized == "none":
        return "None"
    return normalized


def is_function_type(text: str) -> bool:
    return text.startswith("(") and ")->" in text


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
        close = find_matching(self.text, self.i, "(", ")")
        self.i = close + 1
        self.skip_ws()
        if self.text[self.i : self.i + 2] != "->":
            raise SyntaxError(
                err(
                    "E1003",
                    self.lineno,
                    f"invalid type annotation '{self.text}'",
                    "Function types must use `(name: Type, ...) -> ReturnType`.",
                )
            )
        self.i += 2

        params_text = self.text[start + 1 : close]
        params: list[str] = []
        for raw in split_top_level(params_text, ","):
            token_text = raw.strip()
            if not token_text:
                continue
            left, right = split_once_top_level(token_text, ":")
            if left is None or right is None:
                raise SyntaxError(
                    err(
                        "E1003",
                        self.lineno,
                        f"invalid function type parameter '{token_text}'",
                        "Use parameter form `name: Type` inside function types.",
                    )
                )
            param_name = left.strip()
            if not IDENTIFIER_RE.fullmatch(param_name):
                raise SyntaxError(
                    err(
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
                    err(
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

        if not base or not TYPE_BASE_RE.fullmatch(base):
            raise SyntaxError(
                err(
                    "E1003",
                    self.lineno,
                    f"invalid type annotation '{self.text}'",
                    "Use names like int, str, MyType, or function types.",
                )
            )

        if base in RESERVED_WORDS and base not in {"int", "float", "bool", "str", "none"}:
            raise SyntaxError(
                err(
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
