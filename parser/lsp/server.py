from __future__ import annotations

import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from parser.custom_frontend import parse_custom_source as parse_custom
from parser.custom_frontend import FILE_IMPORT_SENTINEL, NATIVE_IMPORT_SENTINEL
from parser.diagnostics import (
    diagnostic_from_exception,
    diagnostic_to_lsp,
    make_diagnostic,
)
from parser.formatter import format_source
from parser.semantics import analyze_semantics, check_semantics
from parser.semantics.models import SemanticAnalysis, SemanticSymbol


JSONValue = dict[str, Any]


@dataclass
class DocumentState:
    uri: str
    path: Path | None
    text: str
    version: int
    last_parse: Any = None
    last_analysis: SemanticAnalysis | None = None
    last_diagnostics: list[JSONValue] = field(default_factory=list)


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
        self.workspace_root: Path | None = None
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
                self._initialize_workspace(params)
                return self._result(request_id, self._initialize_result())

            if method == "shutdown":
                self.logger.info("shutdown")
                self.shutdown_requested = True
                return self._result(request_id, None)

            if method == "textDocument/hover":
                self.logger.info("hover request")
                return self._result(request_id, self._hover(params))

            if method == "textDocument/definition":
                self.logger.info("definition request")
                return self._result(request_id, self._definition(params))

            if method == "textDocument/references":
                self.logger.info("references request")
                return self._result(request_id, self._references(params))

            if method == "textDocument/completion":
                self.logger.info("completion request")
                return self._result(request_id, self._completion(params))

            if method == "textDocument/documentSymbol":
                self.logger.info("document symbol request")
                return self._result(request_id, self._document_symbol(params))

            if method == "textDocument/codeAction":
                self.logger.info("code action request")
                return self._result(request_id, self._code_action(params))

            if method == "textDocument/formatting":
                self.logger.info("formatting request")
                return self._result(request_id, self._formatting(params))

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
                "definitionProvider": True,
                "referencesProvider": True,
                "completionProvider": {
                    "triggerCharacters": ["."],
                },
                "documentSymbolProvider": True,
                "codeActionProvider": True,
                "documentFormattingProvider": True,
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

        path = self._uri_to_path(uri)
        self.documents[uri] = DocumentState(
            uri=uri, path=path, text=text, version=version
        )
        if path is not None:
            self._update_workspace_root(path)
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
        if doc.path is None:
            doc.path = self._uri_to_path(uri)
        if doc.path is not None:
            self._update_workspace_root(doc.path)
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
        try:
            frontend = parse_custom(doc.text)
            doc.last_parse = frontend.tree
            check_semantics(doc.last_parse, project_root=None, source_path=doc.path)
            doc.last_analysis = analyze_semantics(
                doc.last_parse, project_root=None, source_path=doc.path
            )
            doc.last_diagnostics = []
            self.logger.info(f"parse success {uri}")
        except SyntaxError as exc:
            diagnostic = syntax_error_to_lsp_diagnostic(exc, uri=uri)
            doc.last_parse = None
            doc.last_analysis = None
            doc.last_diagnostics = [diagnostic]
            self.logger.info(f"parse failure {uri}: {diagnostic['message']}")
        except Exception as exc:
            self.logger.error(f"parse crash {uri}: {exc}")
            doc.last_parse = None
            doc.last_analysis = None
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
                        "version": doc.version,
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
                "version": doc.version,
                "diagnostics": doc.last_diagnostics,
            },
        }

    def _hover(self, params: Any) -> JSONValue | None:
        symbol, _ = self._resolve_symbol_from_position(params)
        if symbol is None:
            return None
        detail = symbol.detail or symbol.name
        if symbol.type_name:
            detail = f"`{symbol.name}` : `{symbol.type_name}`"
        return {
            "contents": {
                "kind": "markdown",
                "value": f"**{symbol.kind}**\n\n{detail}",
            }
        }

    def _definition(self, params: Any) -> list[JSONValue] | None:
        symbol, doc = self._resolve_symbol_from_position(params)
        if symbol is None or doc is None:
            cross_file = self._definition_from_workspace(params)
            return [cross_file] if cross_file is not None else None
        return [self._symbol_location_to_lsp_location(doc, symbol)]

    def _references(self, params: Any) -> list[JSONValue] | None:
        symbol, doc = self._resolve_symbol_from_position(params)
        if symbol is None or doc is None or doc.last_analysis is None:
            return None
        include_declaration = True
        context = params.get("context", {})
        if isinstance(context, dict):
            include_declaration = bool(context.get("includeDeclaration", True))

        locations: list[JSONValue] = []
        if include_declaration:
            locations.append(self._symbol_location_to_lsp_location(doc, symbol))
        for reference in self._references_for_symbol(
            doc.last_analysis, symbol.qualified_name
        ):
            locations.append(self._range_to_location(doc, reference.location))
        return locations

    def _document_symbol(self, params: Any) -> list[JSONValue] | None:
        doc = self._document_from_params(params)
        if doc is None or doc.last_analysis is None:
            return None
        return [
            self._semantic_symbol_to_document_symbol(doc, symbol)
            for symbol in doc.last_analysis.top_level_symbols
        ]

    def _code_action(self, params: Any) -> list[JSONValue] | None:
        doc = self._document_from_params(params)
        if doc is None:
            return None
        context = params.get("context", {})
        diagnostics = (
            context.get("diagnostics", []) if isinstance(context, dict) else []
        )
        if not diagnostics:
            diagnostics = doc.last_diagnostics
        if not isinstance(diagnostics, list):
            diagnostics = []
        actions: list[JSONValue] = []
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                continue
            action = self._code_action_for_diagnostic(doc, diagnostic)
            if action is not None:
                actions.append(action)
        return actions

    def _formatting(self, params: Any) -> list[JSONValue] | None:
        doc = self._document_from_params(params)
        if doc is None:
            return None
        formatted = format_source(doc.text)
        if formatted == doc.text:
            return []
        return [
            {
                "range": self._full_document_range(doc.text),
                "newText": formatted,
            }
        ]

    def _completion(self, params: Any) -> JSONValue | list[JSONValue] | None:
        doc = self._document_from_params(params)
        if doc is None:
            return None
        position = params.get("position", {})
        if not isinstance(position, dict):
            return []
        line = position.get("line", 0)
        character = position.get("character", 0)
        if not isinstance(line, int) or not isinstance(character, int):
            return []

        line_text = self._line_at(doc.text, line)
        if line_text is None:
            return []

        completion_target = self._attribute_completion_target(line_text, character)
        if completion_target is None:
            return []

        base_name, member_prefix = completion_target
        target_path = self._resolve_module_alias_path(doc, base_name)
        if target_path is None:
            return []

        target_doc = self._load_document_from_path(target_path)
        if target_doc is None or target_doc.last_analysis is None:
            return []

        items: list[JSONValue] = []
        seen: set[str] = set()
        for symbol in self._exported_top_level_symbols(target_doc):
            if symbol.name in seen:
                continue
            if member_prefix and not symbol.name.startswith(member_prefix):
                continue
            seen.add(symbol.name)
            items.append(self._symbol_to_completion_item(symbol))

        return {"isIncomplete": False, "items": items}

    def _resolve_symbol_from_position(
        self, params: Any
    ) -> tuple[SemanticSymbol | None, DocumentState | None]:
        text_document = params.get("textDocument", {})
        position = params.get("position", {})
        uri = text_document.get("uri")
        if not isinstance(uri, str):
            return None, None
        doc = self.documents.get(uri)
        if doc is None or doc.last_analysis is None:
            return None, doc
        line = int(position.get("line", 0))
        character = int(position.get("character", 0))
        symbol = self._symbol_at_position(doc.last_analysis, line, character)
        if symbol is None:
            return None, doc
        return symbol, doc

    def _definition_from_workspace(self, params: Any) -> JSONValue | None:
        doc = self._document_from_params(params)
        if doc is None:
            return None
        position = params.get("position", {})
        if not isinstance(position, dict):
            return None
        line = position.get("line", 0)
        character = position.get("character", 0)
        if not isinstance(line, int) or not isinstance(character, int):
            return None

        line_text = self._line_at(doc.text, line)
        if line_text is None:
            return None

        attribute_target = self._attribute_completion_target(line_text, character)
        if attribute_target is not None:
            alias, _member_prefix = attribute_target
            target_path = self._resolve_module_alias_path(doc, alias)
            if target_path is not None:
                word = word_at_position(doc.text, line, character)
                if word == alias:
                    return self._location_for_path(target_path)
                if word is not None:
                    target_doc = self._load_document_from_path(target_path)
                    if target_doc is not None:
                        symbol = self._find_exported_symbol(target_doc, word)
                        if symbol is not None:
                            return self._symbol_location_to_lsp_location(target_doc, symbol)

        word = word_at_position(doc.text, line, character)
        if word is None:
            return None
        target_path = self._resolve_module_alias_path(doc, word)
        if target_path is not None:
            return self._location_for_path(target_path)
        return None

    def _initialize_workspace(self, params: Any) -> None:
        if not isinstance(params, dict):
            return
        root_uri = params.get("rootUri")
        if isinstance(root_uri, str):
            root = self._uri_to_path(root_uri)
            if root is not None:
                self.workspace_root = root
                return

        workspace_folders = params.get("workspaceFolders")
        if isinstance(workspace_folders, list):
            for folder in workspace_folders:
                if not isinstance(folder, dict):
                    continue
                folder_uri = folder.get("uri")
                if not isinstance(folder_uri, str):
                    continue
                root = self._uri_to_path(folder_uri)
                if root is not None:
                    self.workspace_root = root
                    return

        root_path = params.get("rootPath")
        if isinstance(root_path, str) and root_path:
            self.workspace_root = Path(root_path).resolve()

    def _uri_to_path(self, uri: str) -> Path | None:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        path = unquote(parsed.path)
        if not path:
            return None
        return Path(path).resolve()

    def _update_workspace_root(self, path: Path) -> None:
        path = path.resolve()
        if self.workspace_root is None:
            self.workspace_root = path.parent
            return
        try:
            common = Path(os.path.commonpath([str(self.workspace_root), str(path.parent)]))
        except ValueError:
            return
        self.workspace_root = common

    def _workspace_source_paths(self) -> list[Path]:
        if self.workspace_root is None or not self.workspace_root.exists():
            return []
        source_root = self.workspace_root
        if (self.workspace_root / "src").exists():
            source_root = self.workspace_root / "src"
        return sorted(path.resolve() for path in source_root.rglob("*.ty"))

    def _load_document_from_path(self, path: Path) -> DocumentState | None:
        resolved = path.resolve()
        for doc in self.documents.values():
            if doc.path is not None and doc.path.resolve() == resolved:
                return doc

        try:
            text = resolved.read_text()
        except OSError:
            return None

        uri = resolved.as_uri()
        temp_doc = DocumentState(uri=uri, path=resolved, text=text, version=0)
        self._analyze_document(temp_doc)
        return temp_doc

    def _analyze_document(self, doc: DocumentState) -> None:
        try:
            frontend = parse_custom(doc.text)
            doc.last_parse = frontend.tree
            check_semantics(doc.last_parse, project_root=None, source_path=doc.path)
            doc.last_analysis = analyze_semantics(
                doc.last_parse, project_root=None, source_path=doc.path
            )
            doc.last_diagnostics = []
        except Exception:
            doc.last_parse = None
            doc.last_analysis = None

    def _resolve_module_alias_path(self, doc: DocumentState, alias: str) -> Path | None:
        for name, path in self._module_imports_for_document(doc).items():
            if name == alias:
                return path
        return None

    def _exported_top_level_symbols(self, doc: DocumentState) -> list[SemanticSymbol]:
        if doc.last_analysis is None:
            return []
        imported_aliases = set(self._module_imports_for_document(doc))
        exported: list[SemanticSymbol] = []
        for symbol in doc.last_analysis.top_level_symbols:
            if symbol.name in imported_aliases:
                continue
            if symbol.is_public:
                exported.append(symbol)
        return exported

    def _find_exported_symbol(
        self, doc: DocumentState, name: str
    ) -> SemanticSymbol | None:
        for symbol in self._exported_top_level_symbols(doc):
            if symbol.name == name:
                return symbol
        return None

    def _module_imports_for_document(self, doc: DocumentState) -> dict[str, Path]:
        if doc.last_parse is None:
            return {}
        imports: dict[str, Path] = {}
        module_path = doc.path
        if module_path is None:
            module_path = self._uri_to_path(doc.uri)
        if module_path is None:
            return {}
        if not isinstance(doc.last_parse, ast.Module):
            return {}

        for stmt in doc.last_parse.body:
            if not (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and len(stmt.value.args) == 2
            ):
                continue
            call = stmt.value
            alias = call.args[1]
            if not isinstance(alias, ast.Constant) or not isinstance(alias.value, str):
                continue
            if call.func.id == FILE_IMPORT_SENTINEL:
                raw_path = call.args[0]
                if not isinstance(raw_path, ast.Constant) or not isinstance(
                    raw_path.value, str
                ):
                    continue
                resolved = (module_path.parent / raw_path.value).resolve()
                imports[alias.value] = resolved
            elif call.func.id == NATIVE_IMPORT_SENTINEL:
                raw_target = call.args[0]
                if not isinstance(raw_target, ast.Constant) or not isinstance(
                    raw_target.value, str
                ):
                    continue
                resolved = self._resolve_native_import_path(raw_target.value)
                if resolved is not None:
                    imports[alias.value] = resolved
        return imports

    def _resolve_native_import_path(self, raw: str) -> Path | None:
        if self.workspace_root is None:
            return None
        relative = Path(*raw.split("/")).with_suffix(".ty")
        candidates = [
            (self.workspace_root / "src" / relative).resolve(),
            (self.workspace_root / relative).resolve(),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _attribute_completion_target(
        self, line_text: str, character: int
    ) -> tuple[str, str] | None:
        prefix = line_text[: max(0, character)]
        if not prefix:
            return None
        match = re.search(
            r"(?P<base>[A-Za-z_][A-Za-z0-9_]*)\.(?P<prefix>[A-Za-z_][A-Za-z0-9_]*)?$",
            prefix,
        )
        if match is None:
            return None
        return match.group("base"), match.group("prefix") or ""

    def _line_at(self, text: str, line: int) -> str | None:
        lines = text.splitlines()
        if line < 0 or line >= len(lines):
            return None
        return lines[line]

    def _location_for_path(self, path: Path) -> JSONValue:
        return {
            "uri": path.resolve().as_uri(),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 0},
            },
        }

    def _symbol_to_completion_item(self, symbol: SemanticSymbol) -> JSONValue:
        kind_map = {
            "function": 3,
            "method": 2,
            "class": 7,
            "record": 22,
            "enum": 13,
            "field": 5,
            "constant": 21,
            "variable": 6,
        }
        return {
            "label": symbol.name,
            "kind": kind_map.get(symbol.kind, 6),
            "detail": symbol.detail or symbol.type_name or symbol.kind,
        }

    def _document_from_params(self, params: Any) -> DocumentState | None:
        text_document = params.get("textDocument", {})
        uri = text_document.get("uri")
        if not isinstance(uri, str):
            return None
        return self.documents.get(uri)

    def _symbol_at_position(
        self, analysis: SemanticAnalysis, line: int, character: int
    ) -> SemanticSymbol | None:
        for symbol in self._iter_symbols(analysis.top_level_symbols):
            if self._range_contains(symbol.selection_range, line, character):
                return symbol
        for refs in analysis.references_by_qualified_name.values():
            for reference in refs:
                if self._range_contains(reference.location, line, character):
                    return analysis.symbols_by_qualified_name.get(
                        reference.qualified_name
                    )
        return None

    def _references_for_symbol(
        self, analysis: SemanticAnalysis, qualified_name: str
    ) -> list[Any]:
        return analysis.references_by_qualified_name.get(qualified_name, [])

    def _iter_symbols(self, symbols: list[SemanticSymbol]) -> list[SemanticSymbol]:
        flattened: list[SemanticSymbol] = []
        for symbol in symbols:
            flattened.append(symbol)
            flattened.extend(self._iter_symbols(symbol.children))
        return flattened

    def _semantic_symbol_to_document_symbol(
        self, doc: DocumentState, symbol: SemanticSymbol
    ) -> JSONValue:
        children = [
            self._semantic_symbol_to_document_symbol(doc, child)
            for child in symbol.children
        ]
        return {
            "name": symbol.name,
            "kind": self._lsp_symbol_kind(symbol.kind),
            "range": self._range_to_lsp_range(symbol.location),
            "selectionRange": self._range_to_lsp_range(symbol.selection_range),
            "detail": symbol.detail or symbol.type_name,
            "children": children,
        }

    def _symbol_location_to_lsp_location(
        self, doc: DocumentState, symbol: SemanticSymbol
    ) -> JSONValue:
        return {
            "uri": doc.uri,
            "range": self._range_to_lsp_range(symbol.selection_range),
        }

    def _range_to_location(self, doc: DocumentState, source_range: Any) -> JSONValue:
        return {
            "uri": doc.uri,
            "range": self._range_to_lsp_range(source_range),
        }

    def _range_to_lsp_range(self, source_range: Any) -> JSONValue:
        return {
            "start": {
                "line": max(0, source_range.start[0] - 1),
                "character": max(0, source_range.start[1] - 1),
            },
            "end": {
                "line": max(0, source_range.end[0] - 1),
                "character": max(0, source_range.end[1] - 1),
            },
        }

    def _range_contains(self, source_range: Any, line: int, character: int) -> bool:
        line1 = line + 1
        char1 = character + 1
        start_line, start_char = source_range.start
        end_line, end_char = source_range.end
        if line1 < start_line or line1 > end_line:
            return False
        if start_line == end_line:
            return start_line == line1 and start_char <= char1 < end_char
        if line1 == start_line:
            return char1 >= start_char
        if line1 == end_line:
            return char1 < end_char
        return True

    def _lsp_symbol_kind(self, kind: str) -> int:
        mapping = {
            "module": 1,
            "namespace": 3,
            "class": 5,
            "method": 6,
            "field": 8,
            "variable": 13,
            "constant": 14,
            "function": 12,
            "parameter": 13,
            "record": 5,
            "enum": 10,
        }
        return mapping.get(kind, 13)

    def _code_action_for_diagnostic(
        self, doc: DocumentState, diagnostic: JSONValue
    ) -> JSONValue | None:
        code = diagnostic.get("code")
        if not isinstance(code, str):
            return None
        edits = self._diagnostic_fix_edits(doc.text, diagnostic)
        if not edits:
            return None
        return {
            "title": f"Fix {code}",
            "kind": "quickfix",
            "diagnostics": [diagnostic],
            "edit": {
                "changes": {
                    doc.uri: edits,
                }
            },
        }

    def _diagnostic_fix_edits(
        self, text: str, diagnostic: JSONValue
    ) -> list[JSONValue]:
        code = diagnostic.get("code")
        message = diagnostic.get("message", "")
        if not isinstance(code, str) or not isinstance(message, str):
            return []
        if code == "E1016":
            return self._insert_pass_for_empty_block(text, diagnostic)
        if code == "E2069":
            return [self._replace_range_from_diagnostic(diagnostic, "return none")]
        return []

    def _insert_pass_for_empty_block(
        self, text: str, diagnostic: JSONValue
    ) -> list[JSONValue]:
        lines = text.splitlines()
        range_data = diagnostic.get("range")
        if not isinstance(range_data, dict):
            return []
        start = range_data.get("start", {})
        if not isinstance(start, dict):
            return []
        line = start.get("line")
        if not isinstance(line, int) or line < 0 or line >= len(lines):
            return []
        indent_match = re.match(r"^\s*", lines[line])
        indent = indent_match.group(0) if indent_match else ""
        return [
            {
                "range": {
                    "start": {"line": line, "character": 0},
                    "end": {"line": line, "character": 0},
                },
                "newText": f"{indent}    pass\n",
            }
        ]

    def _replace_range_from_diagnostic(
        self, diagnostic: JSONValue, new_text: str
    ) -> JSONValue:
        return {
            "range": diagnostic.get("range"),
            "newText": new_text,
        }

    def _full_document_range(self, text: str) -> JSONValue:
        lines = text.splitlines() or [""]
        last_line = len(lines) - 1
        last_character = len(lines[-1])
        return {
            "start": {"line": 0, "character": 0},
            "end": {"line": last_line, "character": last_character},
        }

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
    return diagnostic_to_lsp(converted)


def internal_diagnostic(*, uri: str, text: str, message: str) -> JSONValue:
    lines = text.splitlines() or [""]
    diagnostic = make_diagnostic(
        code="P0001",
        severity="internal",
        phase="panic",
        message=message,
        file=uri,
        line=1,
        column=1,
        end_line=1,
        end_column=max(1, len(lines[0])),
        notes=["Internal parser crash"],
    )
    return diagnostic_to_lsp(diagnostic)


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
