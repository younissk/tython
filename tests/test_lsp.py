from __future__ import annotations

from parser.lsp.server import TythonLspServer


def _initialize(server: TythonLspServer) -> dict:
    response = server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        }
    )[0]
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
        },
        "serverInfo": {
            "name": "tython-lsp",
            "version": "0.1.0",
        },
    }


def test_did_open_invalid_publishes_single_diagnostic() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/test.ty"

    server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "version": 1,
                    "text": "record Animal {\n    name str\n}\n",
                }
            },
        }
    )

    publish = server.collect_publish_for_uri(uri)
    assert publish is not None
    diagnostics = publish["params"]["diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["source"] == "tython"


def test_did_change_invalid_to_valid_clears_diagnostic() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/test.ty"

    server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "version": 1,
                    "text": "record Animal {\n    name str\n}\n",
                }
            },
        }
    )
    first = server.collect_publish_for_uri(uri)
    assert first is not None
    assert len(first["params"]["diagnostics"]) == 1

    server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didChange",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "version": 2,
                },
                "contentChanges": [
                    {
                        "text": "record Animal {\n    name: str\n}\n",
                    }
                ],
            },
        }
    )

    second = server.collect_publish_for_uri(uri)
    assert second is not None
    assert second["params"]["diagnostics"] == []


def test_hover_known_and_unknown_symbol() -> None:
    server = TythonLspServer()
    uri = "file:///tmp/test.ty"
    source = (
        "record Animal {\n"
        "    name: str\n"
        "}\n\n"
        "var fish: Animal = Animal {\n"
        '    name: "Nemo"\n'
        "}\n"
    )

    server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "version": 1,
                    "text": source,
                }
            },
        }
    )

    hover_known = server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": 4, "character": 5},
            },
        }
    )[0]
    assert hover_known["result"] is not None
    assert "fish" in hover_known["result"]["contents"]["value"]

    hover_unknown = server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": 1, "character": 6},
            },
        }
    )[0]
    assert hover_unknown["result"] is None


def test_unknown_request_method_returns_protocol_error() -> None:
    server = TythonLspServer()

    response = server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "textDocument/completion",
            "params": {},
        }
    )[0]

    assert response["error"]["code"] == -32601


def test_parse_crash_converts_to_internal_diagnostic(monkeypatch) -> None:
    from parser import lsp

    server = TythonLspServer()
    uri = "file:///tmp/test.ty"

    def _explode(_text: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(lsp.server, "parse_custom", _explode)

    server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "version": 1,
                    "text": "const fish: int = 1\n",
                }
            },
        }
    )

    publish = server.collect_publish_for_uri(uri)
    assert publish is not None
    diagnostics = publish["params"]["diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["message"] == "Internal parser error. Check logs."
