from __future__ import annotations

import io
import re
import token
import tokenize

from .constants import (
    FILE_IMPORT_SENTINEL,
    IDENTIFIER_RE,
    NATIVE_IMPORT_SENTINEL,
    PYIMPORT_SENTINEL,
    RECORD_LITERAL_SENTINEL,
    TRY_PROPAGATE_SENTINEL,
)
from .errors import err
from .helpers import split_once_top_level


def rewrite_record_literal_blocks(source: str) -> str:
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
        if stripped.startswith("}"):
            out.append(line)
            i += 1
            continue

        head = stripped[:-1].rstrip()
        if (
            head.startswith("if ")
            or head.startswith("else")
            or head.startswith("try")
            or head.startswith("catch ")
            or head.startswith("finally")
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
            key, value = split_once_top_level(inner, ":")
            if key is None or value is None:
                raise SyntaxError(
                    err(
                        "E1026",
                        i + 1,
                        "invalid record literal field",
                        "Use `field: expression` entries inside record literals.",
                    )
                )
            field_name = key.strip()
            if not IDENTIFIER_RE.fullmatch(field_name):
                raise SyntaxError(
                    err(
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
                err(
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


def rewrite_this_references(source: str) -> str:
    stream = io.StringIO(source)
    out_tokens: list[tokenize.TokenInfo] = []
    for tok in tokenize.generate_tokens(stream.readline):
        if tok.type == tokenize.NAME and tok.string == "this":
            tok = tokenize.TokenInfo(tok.type, "self", tok.start, tok.end, tok.line)
        out_tokens.append(tok)
    return tokenize.untokenize(out_tokens)


def rewrite_named_call_args(source: str) -> str:
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
            elif last_sig is not None and is_call_paren_after(last_sig):
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


def is_call_paren_after(tok: tokenize.TokenInfo) -> bool:
    if tok.type in {token.NAME, token.NUMBER, token.STRING}:
        return True
    if tok.type == token.OP and tok.string in {")", "]"}:
        return True
    return False


def rewrite_lowercase_literals(source: str) -> str:
    stream = io.StringIO(source)
    out_tokens: list[tokenize.TokenInfo] = []

    for tok in tokenize.generate_tokens(stream.readline):
        if tok.type == tokenize.NAME:
            if tok.string == "true":
                tok = tokenize.TokenInfo(tok.type, "True", tok.start, tok.end, tok.line)
            elif tok.string == "false":
                tok = tokenize.TokenInfo(
                    tok.type, "False", tok.start, tok.end, tok.line
                )
            elif tok.string == "none":
                tok = tokenize.TokenInfo(tok.type, "None", tok.start, tok.end, tok.line)
        out_tokens.append(tok)

    return tokenize.untokenize(out_tokens)


def rewrite_tokens_combined(source: str) -> str:
    """Single tokenize pass that combines:

    - `this` -> `self`
    - lowercase literals: true/false/none -> True/False/None
    - named call args: `f(x: 1)` -> `f(x=1)` (only in call parens)
    """
    stream = io.StringIO(source)
    out_tokens: list[tokenize.TokenInfo] = []

    paren_stack: list[str] = []
    square_depth = 0
    brace_depth = 0

    last_sig: tokenize.TokenInfo | None = None
    second_last_sig: tokenize.TokenInfo | None = None

    for tok in tokenize.generate_tokens(stream.readline):
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
            elif last_sig is not None and is_call_paren_after(last_sig):
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

        if token_type == token.NAME:
            if token_str == "this":
                tok = tokenize.TokenInfo(tok.type, "self", tok.start, tok.end, tok.line)
                token_str = tok.string
            elif token_str == "true":
                tok = tokenize.TokenInfo(tok.type, "True", tok.start, tok.end, tok.line)
                token_str = tok.string
            elif token_str == "false":
                tok = tokenize.TokenInfo(tok.type, "False", tok.start, tok.end, tok.line)
                token_str = tok.string
            elif token_str == "none":
                tok = tokenize.TokenInfo(tok.type, "None", tok.start, tok.end, tok.line)
                token_str = tok.string

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


def rewrite_try_propagation(source: str) -> str:
    lines = source.splitlines()
    out_lines: list[str] = []
    for line in lines:
        out_lines.append(_rewrite_try_in_line(line))
    return "\n".join(out_lines) + "\n"


def rewrite_import_forms(source: str) -> str:
    out: list[str] = []
    pyimport_re = re.compile(
        r"^(?P<indent>[ \t]*)pyimport[ \t]+(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?[ \t]*$"
    )
    file_import_re = re.compile(
        r"^(?P<indent>[ \t]*)import[ \t]+(?P<quote>['\"])(?P<path>.+?)(?P=quote)[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
    )
    native_import_re = re.compile(
        r"^(?P<indent>[ \t]*)import[ \t]+(?P<target>[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)+)[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
    )

    for lineno, line in enumerate(source.splitlines(), start=1):
        code, sep, comment = line.partition("#")
        stripped = code.strip()
        if stripped == "":
            out.append(line)
            continue

        py_match = pyimport_re.match(code)
        if py_match is not None:
            indent = py_match.group("indent")
            module = py_match.group("module")
            alias = py_match.group("alias")
            rendered = f"{indent}{PYIMPORT_SENTINEL}({module!r}, {alias!r})"
            if sep:
                rendered += f"  #{comment}"
            out.append(rendered)
            continue

        file_match = file_import_re.match(code)
        if file_match is not None:
            indent = file_match.group("indent")
            path = file_match.group("path")
            alias = file_match.group("alias")
            rendered = f"{indent}{FILE_IMPORT_SENTINEL}({path!r}, {alias!r})"
            if sep:
                rendered += f"  #{comment}"
            out.append(rendered)
            continue

        native_match = native_import_re.match(code)
        if native_match is not None:
            indent = native_match.group("indent")
            target = native_match.group("target")
            alias = native_match.group("alias")
            rendered = f"{indent}{NATIVE_IMPORT_SENTINEL}({target!r}, {alias!r})"
            if sep:
                rendered += f"  #{comment}"
            out.append(rendered)
            continue

        if stripped.startswith("import ") or stripped.startswith("pyimport "):
            raise SyntaxError(
                err(
                    "E1028",
                    lineno,
                    "invalid import form",
                    'Use one of: `import pkg/mod as alias`, `import "./file.ty" as alias`, `pyimport module [as alias]`.',
                )
            )

        out.append(line)
    return "\n".join(out) + "\n"


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
