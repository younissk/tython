from __future__ import annotations

import json
import re
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


LEGACY_ERROR_RE = re.compile(
    r"^\[(?P<code>[A-Z]\d{4})\] Line (?P<line>\d+): (?P<message>.*?)(?:\. Hint: (?P<hint>.*))?$"
)

DIAGNOSTIC_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class DiagnosticRange:
    start: tuple[int, int]
    end: tuple[int, int]


@dataclass(frozen=True)
class Diagnostic:
    schema_version: str
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


_ERRORS_DOC_URL = (
    "file:///Users/youniss/Documents/GitHub/tython/docs/language/errors.md"
)


def now_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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
        schema_version=DIAGNOSTIC_SCHEMA_VERSION,
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


def diagnostic_to_llm_dict(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "schema_version": diagnostic.schema_version,
        "code": diagnostic.code,
        "phase": diagnostic.phase,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "file": diagnostic.file,
        "range": {
            "start": list(diagnostic.range.start),
            "end": list(diagnostic.range.end),
        },
        "expected": diagnostic.expected,
        "found": diagnostic.found,
        "notes": diagnostic.notes,
        "help": diagnostic.help,
        "related": diagnostic.related,
        "fixes": diagnostic.fixes,
        "recovery": diagnostic.recovery,
        "symbol": diagnostic.symbol,
        "command": diagnostic.command,
        "module": diagnostic.module,
    }


def diagnostic_to_lsp(diagnostic: Diagnostic) -> dict[str, Any]:
    data = diagnostic_to_dict(diagnostic)
    line, column = diagnostic.range.start
    end_line, end_column = diagnostic.range.end
    lsp_range = {
        "start": {"line": max(0, line - 1), "character": max(0, column - 1)},
        "end": {"line": max(0, end_line - 1), "character": max(0, end_column - 1)},
    }
    related_information: list[dict[str, Any]] = []
    for related in diagnostic.related:
        if not isinstance(related, dict):
            continue
        message = related.get("message")
        if not isinstance(message, str):
            continue

        uri = diagnostic.file
        range_data: dict[str, Any] | None = None

        location = related.get("location")
        if isinstance(location, dict):
            location_uri = location.get("uri")
            if isinstance(location_uri, str):
                uri = location_uri
            location_range = location.get("range")
            if isinstance(location_range, dict):
                range_data = location_range
        else:
            related_file = related.get("file")
            if isinstance(related_file, str):
                uri = related_file
            related_range = related.get("range")
            if isinstance(related_range, dict):
                range_data = related_range

        if range_data is None:
            range_data = lsp_range
        related_information.append(
            {
                "location": {
                    "uri": uri,
                    "range": range_data,
                },
                "message": message,
            }
        )

    for note in diagnostic.notes:
        related_information.append(
            {
                "location": {"uri": diagnostic.file, "range": lsp_range},
                "message": note,
            }
        )

    for help_line in diagnostic.help:
        related_information.append(
            {
                "location": {"uri": diagnostic.file, "range": lsp_range},
                "message": help_line,
            }
        )

    href = f"{_ERRORS_DOC_URL}#{quote(diagnostic.code.lower())}"
    payload = {
        "range": lsp_range,
        "severity": 1 if diagnostic.severity in {"error", "internal"} else 2,
        "source": "tython",
        "code": diagnostic.code,
        "codeDescription": {"href": href},
        "message": diagnostic.message,
        "data": data,
    }
    if related_information:
        payload["relatedInformation"] = related_information
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
        parsed = parse_legacy_error_message(
            text, file=file, phase=default_phase, severity="error"
        )
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
            parts.append(f"expected={diagnostic.expected!r} found={diagnostic.found!r}")
        if diagnostic.help:
            parts.append(f"help: {diagnostic.help[0]}")
        return "\n".join(parts)

    if mode == "llm":
        payload = diagnostic_to_llm_dict(diagnostic)
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


def persist_diagnostic_logs(
    diagnostic: Diagnostic, *, export_path: str | None = None
) -> None:
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
