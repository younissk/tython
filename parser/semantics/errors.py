from __future__ import annotations


def err(code: str, lineno: int, message: str, hint: str | None = None) -> str:
    rendered = f"[{code}] Line {lineno}: {message}"
    if hint:
        rendered += f". Hint: {hint}"
    return rendered
