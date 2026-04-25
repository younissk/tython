from __future__ import annotations

from pathlib import Path

from parser.lsp.server import TythonLspServer


BASE_DIR = Path(__file__).parent / "cases" / "lsp"


def _rpc(server: TythonLspServer, method: str, *, request_id: int | None = None, params: dict | None = None):
    payload: dict[str, object] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    responses = server.handle_rpc(payload)
    return responses[0] if responses else None


def _open_document(server: TythonLspServer, uri: str, text: str, version: int = 1) -> None:
    _rpc(
        server,
        "textDocument/didOpen",
        params={
            "textDocument": {
                "uri": uri,
                "version": version,
                "text": text,
            }
        },
    )


def _initialize(server: TythonLspServer) -> dict:
    response = _rpc(server, "initialize", request_id=1, params={})
    assert response is not None
    return response["result"]


def test_initialize_returns_expected_capabilities() -> None:
    server = TythonLspServer()

    result = _initialize(server)

    assert result == {
        "capabilities": {
            "textDocumentSync": {
                "openClose": True,
                "change": 1,
            },
            "hoverProvider": True,
            "definitionProvider": True,
            "referencesProvider": True,
            "documentSymbolProvider": True,
            "codeActionProvider": True,
            "documentFormattingProvider": True,
        },
        "serverInfo": {
            "name": "tython-lsp",
            "version": "0.1.0",
        },
    }


def test_did_open_invalid_publishes_structured_diagnostic() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/test.ty"

    _open_document(server, uri, (BASE_DIR / "invalid" / "empty_block.ty").read_text())

    publish = server.collect_publish_for_uri(uri)
    assert publish is not None
    assert publish["params"]["version"] == 1

    diagnostics = publish["params"]["diagnostics"]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic["source"] == "tython"
    assert diagnostic["code"] == "E1016"
    assert diagnostic["codeDescription"]["href"].endswith("errors.md#e1016")
    assert diagnostic["data"]["code"] == "E1016"
    assert diagnostic["relatedInformation"]


def test_did_change_invalid_to_valid_clears_diagnostic() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/test.ty"

    _open_document(server, uri, (BASE_DIR / "invalid" / "empty_block.ty").read_text())
    first = server.collect_publish_for_uri(uri)
    assert first is not None
    assert len(first["params"]["diagnostics"]) == 1

    _rpc(
        server,
        "textDocument/didChange",
        params={
            "textDocument": {
                "uri": uri,
                "version": 2,
            },
            "contentChanges": [
                {
                    "text": (BASE_DIR / "valid" / "navigation.ty").read_text(),
                }
            ],
        },
    )

    second = server.collect_publish_for_uri(uri)
    assert second is not None
    assert second["params"]["diagnostics"] == []
    assert second["params"]["version"] == 2


def test_hover_definition_references_and_symbols() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/navigation.ty"
    source = (BASE_DIR / "valid" / "navigation.ty").read_text()

    _open_document(server, uri, source)

    hover = _rpc(
        server,
        "textDocument/hover",
        request_id=7,
        params={
            "textDocument": {"uri": uri},
            "position": {"line": 5, "character": 20},
        },
    )
    assert hover is not None
    assert "parameter" in hover["result"]["contents"]["value"]
    assert "name" in hover["result"]["contents"]["value"]

    definition = _rpc(
        server,
        "textDocument/definition",
        request_id=8,
        params={
            "textDocument": {"uri": uri},
            "position": {"line": 5, "character": 20},
        },
    )
    assert definition is not None
    assert definition["result"][0]["uri"] == uri
    assert definition["result"][0]["range"]["start"]["line"] == 4

    references = _rpc(
        server,
        "textDocument/references",
        request_id=9,
        params={
            "textDocument": {"uri": uri},
            "position": {"line": 5, "character": 20},
            "context": {"includeDeclaration": True},
        },
    )
    assert references is not None
    locations = references["result"]
    assert len(locations) >= 2
    assert any(location["range"]["start"]["line"] == 4 for location in locations)
    assert any(location["range"]["start"]["line"] == 5 for location in locations)

    symbols = _rpc(
        server,
        "textDocument/documentSymbol",
        request_id=10,
        params={"textDocument": {"uri": uri}},
    )
    assert symbols is not None
    names = [entry["name"] for entry in symbols["result"]]
    assert names == ["Animal", "greet", "fish"]
    animal_children = symbols["result"][0]["children"]
    assert [entry["name"] for entry in animal_children] == ["name"]


def test_formatting_returns_full_document_edit() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/messy.ty"
    source = (Path(__file__).parent / "cases" / "formatter" / "messy.ty").read_text()

    _open_document(server, uri, source)

    result = _rpc(
        server,
        "textDocument/formatting",
        request_id=11,
        params={"textDocument": {"uri": uri}},
    )
    assert result is not None
    edits = result["result"]
    assert len(edits) == 1
    assert edits[0]["newText"] == (Path(__file__).parent / "cases" / "formatter" / "messy.expected.ty").read_text()


def test_code_action_offers_empty_block_fix() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/empty_block.ty"
    source = (BASE_DIR / "invalid" / "empty_block.ty").read_text()

    _open_document(server, uri, source)
    publish = server.collect_publish_for_uri(uri)
    assert publish is not None

    result = _rpc(
        server,
        "textDocument/codeAction",
        request_id=12,
        params={
            "textDocument": {"uri": uri},
            "range": publish["params"]["diagnostics"][0]["range"],
            "context": {"diagnostics": publish["params"]["diagnostics"]},
        },
    )
    assert result is not None
    actions = result["result"]
    assert actions
    assert actions[0]["kind"] == "quickfix"
    assert "pass" in actions[0]["edit"]["changes"][uri][0]["newText"]


def test_unknown_request_method_returns_protocol_error() -> None:
    server = TythonLspServer()

    response = _rpc(server, "textDocument/completion", request_id=99, params={})
    assert response is not None
    assert response["error"]["code"] == -32601


def test_parse_crash_converts_to_internal_diagnostic(monkeypatch) -> None:
    from parser import lsp

    server = TythonLspServer()
    uri = "file:///tmp/test.ty"

    def _explode(_text: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(lsp.server, "parse_custom", _explode)

    _open_document(server, uri, "const fish: int = 1\n")

    publish = server.collect_publish_for_uri(uri)
    assert publish is not None
    diagnostics = publish["params"]["diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["message"] == "Internal parser error. Check logs."
