from pathlib import Path

import pytest

from parser.formatter import format_file, format_source


BASE_DIR = Path(__file__).parent / "cases" / "formatter"


def _expected_path(source_path: Path) -> Path:
    return source_path.with_name(source_path.name.replace(".ty", ".expected.ty"))


@pytest.mark.parametrize(
    "source_path",
    sorted(
        path
        for path in BASE_DIR.glob("*.ty")
        if not path.name.endswith(".expected.ty")
    ),
)
def test_formatter_fixture_roundtrip(source_path: Path) -> None:
    source = source_path.read_text()
    expected = _expected_path(source_path).read_text()

    assert format_source(source) == expected


@pytest.mark.parametrize(
    "source_path",
    sorted(
        path
        for path in BASE_DIR.glob("*.ty")
        if not path.name.endswith(".expected.ty")
    ),
)
def test_formatter_idempotent(source_path: Path) -> None:
    source = source_path.read_text()
    formatted = format_source(source)

    assert format_source(formatted) == formatted


def test_format_file_rewrites_in_place(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.ty"
    source_path.write_text(
        'import ". / hello.ty" as hello\n\nfunc greet(name: str){\nreturn  "hi, " + name\n}\n'
    )

    changed = format_file(source_path)

    assert changed is True
    assert source_path.read_text() == (
        'import "./hello.ty" as hello\n\nfunc greet(name: str) {\n'
        '    return "hi, " + name\n}\n'
    )
