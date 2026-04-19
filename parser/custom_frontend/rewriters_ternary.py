from __future__ import annotations

from .errors import err


def rewrite_ternary_expressions(source: str) -> str:
    lines = source.splitlines()
    out_lines: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        out_lines.append(rewrite_ternary_in_line(line, lineno))
    return "\n".join(out_lines) + "\n"


def rewrite_ternary_in_line(line: str, lineno: int) -> str:
    if "if" not in line or ":" not in line or "else" not in line:
        return line

    i = 0
    out: list[str] = []
    while i < len(line):
        if not is_word_at(line, i, "if"):
            out.append(line[i])
            i += 1
            continue

        if is_statement_if_position(line, i):
            out.append("if")
            i += 2
            continue

        prev = previous_non_space(line, i)
        if prev is not None and prev in "+-*/%<>=!&|^":
            raise SyntaxError(
                err(
                    "E1018",
                    lineno,
                    "ternary used as operator subexpression must be parenthesized",
                    "Wrap ternary with parentheses when embedding in operator expressions.",
                )
            )

        replacement, next_i = parse_prefix_ternary(line, i, lineno)
        out.append(replacement)
        i = next_i

    return "".join(out)


def parse_prefix_ternary(text: str, start: int, lineno: int) -> tuple[str, int]:
    cond_start = start + 2
    while cond_start < len(text) and text[cond_start].isspace():
        cond_start += 1

    cond_end = find_top_level_colon(text, cond_start)
    if cond_end is None:
        raise SyntaxError(err("E1017", lineno, "invalid ternary syntax", "Use `if cond: expr else expr`."))

    true_start = cond_end + 1
    while true_start < len(text) and text[true_start].isspace():
        true_start += 1

    else_start = find_top_level_else(text, true_start)
    if else_start is None:
        raise SyntaxError(err("E1017", lineno, "invalid ternary syntax", "Use `if cond: expr else expr`."))

    false_start = else_start + 4
    while false_start < len(text) and text[false_start].isspace():
        false_start += 1

    false_end = find_ternary_false_end(text, false_start)

    cond = text[cond_start:cond_end].strip()
    true_expr = text[true_start:else_start].strip()
    false_expr = text[false_start:false_end].strip()
    if not cond or not true_expr or not false_expr:
        raise SyntaxError(err("E1017", lineno, "invalid ternary syntax", "Use `if cond: expr else expr`."))

    return f"({true_expr} if {cond} else {false_expr})", false_end


def find_top_level_colon(text: str, start: int) -> int | None:
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


def find_top_level_else(text: str, start: int) -> int | None:
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
        elif paren == 0 and square == 0 and brace == 0 and is_word_at(text, i, "else"):
            return i
        i += 1
    return None


def find_ternary_false_end(text: str, start: int) -> int:
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


def is_statement_if_position(text: str, if_index: int) -> bool:
    prefix = text[:if_index]
    if prefix.strip() == "":
        return find_top_level_else(text, if_index + 2) is None
    if prefix.rstrip().endswith("else "):
        return True
    return False


def is_word_at(text: str, index: int, word: str) -> bool:
    end = index + len(word)
    if end > len(text):
        return False
    if text[index:end] != word:
        return False
    left_ok = index == 0 or (not text[index - 1].isalnum() and text[index - 1] != "_")
    right_ok = end == len(text) or (not text[end].isalnum() and text[end] != "_")
    return left_ok and right_ok


def previous_non_space(text: str, index: int) -> str | None:
    i = index - 1
    while i >= 0:
        if not text[i].isspace():
            return text[i]
        i -= 1
    return None
