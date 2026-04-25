from pathlib import Path

from parser.formatter import format_source


BASE_DIR = Path(__file__).parent / "cases" / "formatter"


def test_formatter_fixture_roundtrip() -> None:
    source = (BASE_DIR / "messy.ty").read_text()
    expected = (BASE_DIR / "messy.expected.ty").read_text()

    assert format_source(source) == expected


def test_formatter_idempotent() -> None:
    source = (BASE_DIR / "messy.ty").read_text()
    formatted = format_source(source)

    assert format_source(formatted) == formatted
