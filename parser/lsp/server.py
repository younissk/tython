from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from parser import parse_custom
from parser.diagnostics import diagnostic_from_exception


JSONValue = dict[str, Any]


@dataclass
class DocumentState:
    text: str
    version: int
    last_parse: Any = None
    last_diagnostics: list[JSONValue] = field(default_factory=list)
    symbols: dict[str, str] = field(default_factory=dict)


class Logger:
    def __init__(self) -> None:
        self._path = os.getenv("TYTHON_LSP_LOG")

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def _write(self, level: str, message: str) -> None:
        line = f"[{level}] {message}"
        print(line, file=sys.stderr, flush=True)
        if self._path:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            with Path(self._path).open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


class TythonLspServer:
    def __init__(self, *, logger: Logger | None = None) -> None:
        self.logger = logger or Logger()
        self.documents: dict[str, DocumentState] = {}
        self.shutdown_requested = False
        self.exit_requested = False
        self.logger.info("server start")

    def handle_rpc(self, payload: JSONValue) -> list[JSONValue]:
        if not isinstance(payload, dict):
            return [self._error(None, -32600, "Invalid Request")]

        if payload.get("jsonrpc") != "2.0":
            error_id = payload.get("id") if isinstance(payload, dict) else None
            return [self._error(error_id, -32600, "Invalid Request")]

        method = payload.get("method")
        if not isinstance(method, str):
            return [self._error(payload.get("id"), -32600, "Invalid Request")]

        params = payload.get("params")
        request_id = payload.get("id")

        if request_id is None:
            self._handle_notification(method, params)
            return []

        return [self._handle_request(request_id, method, params)]

    def _handle_request(self, request_id: Any, method: str, params: Any) -> JSONValue:
        try:
            if method == "initialize":
                self.logger.info("initialize")
                return self._result(request_id, self._initialize_result())

            if method == "shutdown":
                self.logger.info("shutdown")
                self.shutdown_requested = True
                return self._result(request_id, None)

            if method == "textDocument/hover":
                self.logger.info("hover request")
                return self._result(request_id, self._hover(params))

            return self._error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:  # pragma: no cover - safety boundary
            self.logger.error(f"request {method} failed: {exc}")
            return self._error(request_id, -32603, "Internal error")

    def _handle_notification(self, method: str, params: Any) -> None:
        try:
            if method == "initialized":
                return
            if method == "exit":
                self.exit_requested = True
                return
            if method == "textDocument/didOpen":
                self._did_open(params)
                return
            if method == "textDocument/didChange":
                self._did_change(params)
                return
            if method == "textDocument/didClose":
                self._did_close(params)
                return
        except Exception as exc:  # pragma: no cover - safety boundary
            self.logger.error(f"notification {method} failed: {exc}")

    def _initialize_result(self) -> JSONValue:
        return {
            "capabilities": {
                "textDocumentSync": {
                    "openClose": True,
                    "change": 1,
                },
                "hoverProvider": True,
            },
            "serverInfo": {
                "name": "tython-lsp",
                "version": "0.1.0",
            },
        }

    def _did_open(self, params: Any) -> None:
        text_document = params.get("textDocument", {})
        uri = text_document.get("uri")
        if not isinstance(uri, str):
            return

        text = text_document.get("text")
        if not isinstance(text, str):
            text = ""

        version = text_document.get("version")
        if not isinstance(version, int):
            version = 0

        self.documents[uri] = DocumentState(text=text, version=version)
        self.logger.info(f"open {uri}")
        self._reparse_and_collect(uri)

    def _did_change(self, params: Any) -> None:
        text_document = params.get("textDocument", {})
        uri = text_document.get("uri")
        if not isinstance(uri, str):
            return

        doc = self.documents.get(uri)
        if doc is None:
            return

        content_changes = params.get("contentChanges", [])
        if not content_changes:
            return

        latest = content_changes[-1].get("text")
        if not isinstance(latest, str):
            latest = ""

        version = text_document.get("version")
        if isinstance(version, int):
            doc.version = version

        doc.text = latest
        self.logger.info(f"change {uri}")
        self._reparse_and_collect(uri)

    def _did_close(self, params: Any) -> None:
        text_document = params.get("textDocument", {})
        uri = text_document.get("uri")
        if not isinstance(uri, str):
            return

        self.documents.pop(uri, None)
        self.logger.info(f"close {uri}")

    def _reparse_and_collect(self, uri: str) -> None:
        doc = self.documents[uri]
        doc.symbols = extract_top_level_symbols(doc.text)
        try:
            doc.last_parse = parse_custom(doc.text)
            doc.last_diagnostics = []
            self.logger.info(f"parse success {uri}")
        except SyntaxError as exc:
            diagnostic = syntax_error_to_lsp_diagnostic(exc, uri=uri)
            doc.last_parse = None
            doc.last_diagnostics = [diagnostic]
            self.logger.info(f"parse failure {uri}: {diagnostic['message']}")
        except Exception as exc:
            self.logger.error(f"parse crash {uri}: {exc}")
            doc.last_parse = None
            doc.last_diagnostics = [
                internal_diagnostic(
                    uri=uri, text=doc.text, message="Internal parser error. Check logs."
                )
            ]

    def pop_pending_notifications(self) -> list[JSONValue]:
        notifications: list[JSONValue] = []
        for uri, doc in self.documents.items():
            notifications.append(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/publishDiagnostics",
                    "params": {
                        "uri": uri,
                        "diagnostics": doc.last_diagnostics,
                    },
                }
            )
        return notifications

    def collect_publish_for_uri(self, uri: str) -> JSONValue | None:
        doc = self.documents.get(uri)
        if doc is None:
            return None
        return {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": doc.last_diagnostics,
            },
        }

    def _hover(self, params: Any) -> JSONValue | None:
        text_document = params.get("textDocument", {})
        position = params.get("position", {})
        uri = text_document.get("uri")
        if not isinstance(uri, str):
            return None

        doc = self.documents.get(uri)
        if doc is None:
            return None

        try:
            line = int(position.get("line", 0))
            character = int(position.get("character", 0))
            name = word_at_position(doc.text, line, character)
            if name is None:
                return None
            value = doc.symbols.get(name)
            if value is None:
                return None
            return {
                "contents": {
                    "kind": "markdown",
                    "value": value,
                }
            }
        except Exception as exc:
            self.logger.error(f"hover crash {uri}: {exc}")
            return None

    @staticmethod
    def _result(request_id: Any, result: Any) -> JSONValue:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> JSONValue:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }


def word_at_position(text: str, line: int, character: int) -> str | None:
    lines = text.splitlines()
    if line < 0 or line >= len(lines):
        return None

    raw = lines[line]
    if not raw:
        return None

    idx = max(0, min(character, len(raw) - 1))
    if not (raw[idx].isalnum() or raw[idx] == "_"):
        if idx > 0 and (raw[idx - 1].isalnum() or raw[idx - 1] == "_"):
            idx -= 1
        else:
            return None

    start = idx
    while start > 0 and (raw[start - 1].isalnum() or raw[start - 1] == "_"):
        start -= 1

    end = idx
    while end + 1 < len(raw) and (raw[end + 1].isalnum() or raw[end + 1] == "_"):
        end += 1

    return raw[start : end + 1]


DECL_RE = re.compile(
    r"^\s*(?:pub\s+)?(?:init\s+)?(?P<kind>var|const)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)
RECORD_RE = re.compile(r"^\s*record\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
CLASS_RE = re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
FUNC_RE = re.compile(r"^\s*func\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")


def extract_top_level_symbols(text: str) -> dict[str, str]:
    symbols: dict[str, str] = {}
    depth = 0

    for line in text.splitlines():
        if depth == 0:
            bound = DECL_RE.match(line)
            if bound:
                kind = bound.group("kind")
                name = bound.group("name")
                if kind == "const":
                    symbols[name] = f"`{name}`\n\nA module-level constant."
                else:
                    symbols[name] = f"`{name}`\n\nA module-level variable."

            record = RECORD_RE.match(line)
            if record:
                name = record.group("name")
                symbols[name] = f"`{name}: record`\n\nA record type declaration."

            klass = CLASS_RE.match(line)
            if klass:
                name = klass.group("name")
                symbols[name] = f"`{name}: class`\n\nA class type declaration."

            func = FUNC_RE.match(line)
            if func:
                name = func.group("name")
                symbols[name] = f"`{name}(...): func`\n\nA module-level function."

        depth += line.count("{")
        depth -= line.count("}")
        if depth < 0:
            depth = 0

    return symbols


def syntax_error_to_lsp_diagnostic(error: SyntaxError, *, uri: str) -> JSONValue:
    converted = diagnostic_from_exception(
        error,
        file=uri,
        include_trace=False,
        default_phase="parse",
    )

    start_line = max(0, converted.range.start[0] - 1)
    start_char = max(0, converted.range.start[1] - 1)
    end_line = max(start_line, converted.range.end[0] - 1)
    end_char = max(start_char + 1, converted.range.end[1] - 1)

    return {
        "range": {
            "start": {"line": start_line, "character": start_char},
            "end": {"line": end_line, "character": end_char},
        },
        "severity": 1,
        "source": "tython",
        "message": converted.message,
    }


def internal_diagnostic(*, uri: str, text: str, message: str) -> JSONValue:
    _ = uri
    lines = text.splitlines() or [""]
    return {
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": max(1, len(lines[0]))},
        },
        "severity": 1,
        "source": "tython",
        "message": message,
    }


class StdioTransport:
    def __init__(self, *, input_stream: Any = None, output_stream: Any = None) -> None:
        self.input = input_stream or sys.stdin.buffer
        self.output = output_stream or sys.stdout.buffer

    def read_message(self) -> JSONValue | None:
        headers: dict[str, str] = {}

        while True:
            line = self.input.readline()
            if not line:
                return None
            if line in {b"\r\n", b"\n"}:
                break

            decoded = line.decode("ascii", errors="replace").strip()
            if ":" not in decoded:
                continue
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        content_length = headers.get("content-length")
        if content_length is None:
            return None

        body = self.input.read(int(content_length))
        return json.loads(body.decode("utf-8"))

    def write_message(self, payload: JSONValue) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.output.write(header)
        self.output.write(body)
        self.output.flush()


def main() -> None:
    server = TythonLspServer()
    transport = StdioTransport()

    while True:
        try:
            incoming = transport.read_message()
        except json.JSONDecodeError:
            transport.write_message(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error",
                    },
                }
            )
            continue
        except Exception as exc:  # pragma: no cover - hard safety boundary
            server.logger.error(f"read error: {exc}")
            break

        if incoming is None:
            break

        responses = server.handle_rpc(incoming)
        for response in responses:
            transport.write_message(response)

        method = incoming.get("method")
        if method in {"textDocument/didOpen", "textDocument/didChange"}:
            uri = incoming.get("params", {}).get("textDocument", {}).get("uri")
            if isinstance(uri, str):
                publish = server.collect_publish_for_uri(uri)
                if publish is not None:
                    transport.write_message(publish)

        if server.exit_requested:
            break


if __name__ == "__main__":
    main()
