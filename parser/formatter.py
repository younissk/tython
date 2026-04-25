from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

_FILE_IMPORT_RE = re.compile(
    r'^\s*import\s+(?P<quote>["\'])(?P<path>.*?)(?P=quote)\s+as\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s*$'
)
_NATIVE_IMPORT_RE = re.compile(
    r"^\s*import\s+(?P<target>[A-Za-z_][A-Za-z0-9_]*(?:\s*/\s*[A-Za-z_][A-Za-z0-9_]*)+)\s+as\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s*$"
)
_PYIMPORT_RE = re.compile(
    r"^\s*pyimport\s+(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:\s+as\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?\s*$"
)
_OPENERS = {"(", "[", "{"}
_CLOSERS = {")", "]", "}"}
_SPACED_OPERATORS = {
    "=",
    "==",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "->",
}


def format_source(source: str) -> str:
    source = source.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")

    formatted: list[str] = []
    indent = 0

    for raw_line in lines:
        line = raw_line.rstrip()
        code, comment = _split_trailing_comment(line)
        stripped = code.strip()

        if stripped == "" and comment == "":
            formatted.append("")
            continue

        closing = 0
        while closing < len(stripped) and stripped[closing] == "}":
            indent = max(0, indent - 1)
            closing += 1

        body = stripped[closing:].lstrip()
        if body == "":
            rendered = "    " * indent + "}" * closing
            if comment:
                rendered = f"{rendered} {comment}"
            formatted.append(rendered)
            continue

        opens_block = body.endswith("{")
        if opens_block:
            body = body[:-1].rstrip()

        body = _normalize_import_line(body) or _normalize_inline(body)
        rendered_body = body + (" {" if opens_block else "")
        rendered = "    " * indent + rendered_body
        if comment:
            rendered = f"{rendered} {comment}"
        formatted.append(rendered)

        if opens_block:
            indent += 1

    while formatted and formatted[-1] == "":
        formatted.pop()

    return "\n".join(formatted) + "\n"


def format_file(path: Path) -> bool:
    original = path.read_text()
    formatted = format_source(original)
    if formatted == original:
        return False
    path.write_text(formatted)
    return True


def _split_trailing_comment(text: str) -> tuple[str, str]:
    reader = io.StringIO(text).readline
    try:
        for tok in tokenize.generate_tokens(reader):
            if tok.type == tokenize.COMMENT:
                return text[: tok.start[1]].rstrip(), tok.string
    except tokenize.TokenError:
        pass
    return text, ""


def _normalize_import_line(text: str) -> str | None:
    file_match = _FILE_IMPORT_RE.fullmatch(text)
    if file_match is not None:
        path = re.sub(r"\s*([./])\s*", r"\1", file_match.group("path").strip())
        alias = file_match.group("alias")
        quote = file_match.group("quote")
        return f"import {quote}{path}{quote} as {alias}"

    native_match = _NATIVE_IMPORT_RE.fullmatch(text)
    if native_match is not None:
        target = re.sub(r"\s*/\s*", "/", native_match.group("target").strip())
        alias = native_match.group("alias")
        return f"import {target} as {alias}"

    py_match = _PYIMPORT_RE.fullmatch(text)
    if py_match is not None:
        module = py_match.group("module").strip()
        alias = py_match.group("alias")
        if alias is None:
            return f"pyimport {module}"
        return f"pyimport {module} as {alias}"

    return None


def _normalize_inline(text: str) -> str:
    text = text.strip()
    reader = io.StringIO(text).readline
    parts: list[str] = []
    previous: tokenize.TokenInfo | None = None

    for tok in tokenize.generate_tokens(reader):
        if tok.type in {
            tokenize.ENDMARKER,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
        }:
            continue
        if tok.type == tokenize.COMMENT:
            break
        if previous is not None and _needs_space(previous, tok):
            parts.append(" ")
        parts.append(tok.string)
        previous = tok

    return "".join(parts).strip()


def _needs_space(previous: tokenize.TokenInfo, current: tokenize.TokenInfo) -> bool:
    if previous.type == tokenize.OP and previous.string in {"(", "[", "{", ".", ","}:
        return False
    if current.type == tokenize.OP and current.string in {")", "]", "}", ".", ","}:
        return False
    if previous.type == tokenize.OP and previous.string == ":":
        return True
    if current.type == tokenize.OP and current.string in _SPACED_OPERATORS | {"{"}:
        return True
    if previous.type == tokenize.OP and previous.string in _SPACED_OPERATORS:
        return True
    if current.type in {tokenize.NAME, tokenize.NUMBER, tokenize.STRING} and previous.type in {
        tokenize.NAME,
        tokenize.NUMBER,
        tokenize.STRING,
    }:
        return True
    if current.type == tokenize.OP and current.string == "(":
        return False
    if previous.type == tokenize.OP and previous.string in {")", "]", "}"}:
        return current.type in {tokenize.NAME, tokenize.NUMBER, tokenize.STRING}
    return False
