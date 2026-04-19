def err(code: str, lineno: int, message: str, hint: str) -> str:
    return f"[{code}] Line {lineno}: {message}. Hint: {hint}"
