from __future__ import annotations

from ..diagnostics import format_legacy_error_message, make_diagnostic


def err(code: str, lineno: int, message: str, hint: str | None = None) -> str:
    diagnostic = make_diagnostic(
        code=code,
        severity="error",
        phase="typecheck",
        message=message,
        line=lineno,
        help_lines=[hint] if hint else None,
    )
    return format_legacy_error_message(diagnostic)
