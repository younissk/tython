from __future__ import annotations

import json
import re
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGACY_ERROR_RE = re.compile(
    r"^\[(?P<code>[A-Z]\d{4})\] Line (?P<line>\d+): (?P<message>.*?)(?:\. Hint: (?P<hint>.*))?$"
)


@dataclass(frozen=True)
class DiagnosticRange:
    start: tuple[int, int]
    end: tuple[int, int]


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    phase: str
    message: str
    file: str
    range: DiagnosticRange
    timestamp: str
    expected: str | None = None
    found: str | None = None
    notes: list[str] = field(default_factory=list)
    help: list[str] = field(default_factory=list)
    related: list[dict[str, Any]] = field(default_factory=list)
    trace: list[str] | None = None
    fixes: list[dict[str, Any]] = field(default_factory=list)
    recovery: dict[str, Any] | None = None
    symbol: str | None = None
    command: str | None = None
    module: str | None = None


def now_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_diagnostic(
    *,
    code: str,
    severity: str,
    phase: str,
    message: str,
    file: str = "<input>",
    line: int = 1,
    column: int = 1,
    end_line: int | None = None,
    end_column: int | None = None,
    expected: str | None = None,
    found: str | None = None,
    notes: list[str] | None = None,
    help_lines: list[str] | None = None,
    related: list[dict[str, Any]] | None = None,
    trace: list[str] | None = None,
    fixes: list[dict[str, Any]] | None = None,
    recovery: dict[str, Any] | None = None,
    symbol: str | None = None,
    command: str | None = None,
    module: str | None = None,
) -> Diagnostic:
    line = max(1, line)
    column = max(1, column)
    end_line = max(line, end_line or line)
    end_column = max(column, end_column or column)
    return Diagnostic(
        code=code,
        severity=severity,
        phase=phase,
        message=message,
        file=file,
        range=DiagnosticRange(start=(line, column), end=(end_line, end_column)),
        timestamp=now_timestamp(),
        expected=expected,
        found=found,
        notes=list(notes or []),
        help=list(help_lines or []),
        related=list(related or []),
        trace=trace,
        fixes=list(fixes or []),
        recovery=recovery,
        symbol=symbol,
        command=command,
        module=module,
    )


def diagnostic_to_dict(diagnostic: Diagnostic) -> dict[str, Any]:
    payload = asdict(diagnostic)
    payload["range"] = {
        "start": list(diagnostic.range.start),
        "end": list(diagnostic.range.end),
    }
    return payload


def format_legacy_error_message(diagnostic: Diagnostic) -> str:
    line = diagnostic.range.start[0]
    text = f"[{diagnostic.code}] Line {line}: {diagnostic.message}"
    if diagnostic.help:
        text += f". Hint: {diagnostic.help[0]}"
    return text


def parse_legacy_error_message(
    text: str,
    *,
    file: str,
    phase: str,
    severity: str = "error",
) -> Diagnostic | None:
    match = LEGACY_ERROR_RE.match(text.strip())
    if match is None:
        return None
    hint = match.group("hint")
    return make_diagnostic(
        code=match.group("code"),
        severity=severity,
        phase=phase,
        message=match.group("message"),
        file=file,
        line=int(match.group("line")),
        help_lines=[hint] if hint else None,
    )


def diagnostic_from_exception(
    error: Exception,
    *,
    file: str,
    include_trace: bool,
    default_phase: str,
) -> Diagnostic:
    text = str(error)
    if isinstance(error, SyntaxError):
        parsed = parse_legacy_error_message(text, file=file, phase=default_phase, severity="error")
        if parsed is not None:
            return parsed
        return make_diagnostic(
            code="E9001",
            severity="error",
            phase=default_phase,
            message=text or "syntax error",
            file=file,
            line=getattr(error, "lineno", 1) or 1,
            column=getattr(error, "offset", 1) or 1,
        )

    is_panic = type(error).__name__ == "__TythonPanic" or default_phase == "panic"
    severity = "internal" if is_panic else "error"
    code = "P0001" if is_panic else "R0001"
    message = text or type(error).__name__
    trace_lines = traceback.format_exc().strip().splitlines() if include_trace else None
    return make_diagnostic(
        code=code,
        severity=severity,
        phase="panic" if is_panic else default_phase,
        message=message,
        file=file,
        line=1,
        column=1,
        notes=[type(error).__name__],
        trace=trace_lines,
    )


def render_diagnostic(
    diagnostic: Diagnostic,
    *,
    mode: str,
    verbose: bool,
) -> str:
    line, column = diagnostic.range.start
    location = f"{diagnostic.file}:{line}:{column}"

    if mode == "json":
        return json.dumps(diagnostic_to_dict(diagnostic), ensure_ascii=False, indent=2)
    if mode == "jsonl":
        return json.dumps(diagnostic_to_dict(diagnostic), ensure_ascii=False)

    if mode == "compact":
        parts = [
            f"{diagnostic.severity}[{diagnostic.code}] {location} {diagnostic.message}",
        ]
        if diagnostic.expected is not None or diagnostic.found is not None:
            parts.append(
                f"expected={diagnostic.expected!r} found={diagnostic.found!r}"
            )
        if diagnostic.help:
            parts.append(f"help: {diagnostic.help[0]}")
        return "\n".join(parts)

    if mode == "llm":
        payload = {
            "code": diagnostic.code,
            "phase": diagnostic.phase,
            "severity": diagnostic.severity,
            "message": diagnostic.message,
            "file": diagnostic.file,
            "line": line,
            "column": column,
            "help": diagnostic.help,
        }
        return (
            f"{diagnostic.severity}[{diagnostic.code}] {location} {diagnostic.message}\n"
            f"llm_fields: {json.dumps(payload, ensure_ascii=False)}"
        )

    parts = [
        f"{diagnostic.severity}[{diagnostic.code}] {location}",
        diagnostic.message,
    ]
    if diagnostic.notes:
        parts.extend(f"note: {note}" for note in diagnostic.notes)
    if diagnostic.help:
        parts.extend(f"help: {entry}" for entry in diagnostic.help)
    if verbose and diagnostic.trace:
        parts.append("trace:")
        parts.extend(diagnostic.trace)
    return "\n".join(parts)


def persist_diagnostic_logs(diagnostic: Diagnostic, *, export_path: str | None = None) -> None:
    payload = json.dumps(diagnostic_to_dict(diagnostic), ensure_ascii=False)
    root = Path(".project") / "errors"
    root.mkdir(parents=True, exist_ok=True)

    latest_path = root / "latest.jsonl"
    latest_path.write_text(payload + "\n")

    timestamp = diagnostic.timestamp.replace(":", "-")
    stamped_path = root / f"{timestamp}.jsonl"
    stamped_path.write_text(payload + "\n")

    if export_path:
        path = Path(export_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n")
