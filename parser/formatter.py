from __future__ import annotations

import re
from pathlib import Path

_SPACE_AROUND = re.compile(r"\s*([,:=+\-*/%<>]+)\s*")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,)\]])")
_SPACE_AFTER_PUNCT = re.compile(r"([({\[])\s+")


def format_source(source: str) -> str:
    source = source.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")

    formatted: list[str] = []
    indent = 0

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped == "":
            formatted.append("")
            continue

        closing = 0
        while closing < len(stripped) and stripped[closing] == "}":
            indent = max(0, indent - 1)
            closing += 1

        body = stripped[closing:].lstrip()
        if body == "":
            formatted.append("    " * indent + "}" * closing)
            continue

        body = _normalize_inline(body)
        formatted.append("    " * indent + body)

        if body.endswith("{"):
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


def _normalize_inline(text: str) -> str:
    text = text.strip()
    text = text.replace("{", " {")
    text = _SPACE_AROUND.sub(r" \1 ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_PUNCT.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text)
    text = text.replace("( ", "(").replace(" )", ")")
    text = text.replace("[ ", "[").replace(" ]", "]")
    text = text.replace("{ ", "{").replace(" }", "}")
    text = text.replace(" :", ":").replace(" ,", ",")
    text = text.replace("= ", " = ").replace(" -> ", " -> ")
    return text.strip()
