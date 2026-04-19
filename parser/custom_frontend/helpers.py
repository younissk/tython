from __future__ import annotations

from .errors import err


def split_top_level(text: str, delimiter: str) -> list[str]:
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


def split_once_top_level(text: str, delimiter: str) -> tuple[str | None, str | None]:
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


def find_matching(text: str, start: int, opener: str, closer: str) -> int:
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
            "E1015",
            1,
            f"unmatched '{opener}'",
            f"Ensure every `{opener}` has a matching `{closer}`.",
        )
    )
