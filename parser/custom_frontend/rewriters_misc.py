from __future__ import annotations

import io
import re
import token
import tokenize

from .constants import IDENTIFIER_RE, RECORD_LITERAL_SENTINEL
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
        out.append(f"{indent}{prefix}{RECORD_LITERAL_SENTINEL}({type_name!r}, [{rendered}])")
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
                tok = tokenize.TokenInfo(tok.type, "False", tok.start, tok.end, tok.line)
            elif tok.string == "none":
                tok = tokenize.TokenInfo(tok.type, "None", tok.start, tok.end, tok.line)
        out_tokens.append(tok)

    return tokenize.untokenize(out_tokens)
