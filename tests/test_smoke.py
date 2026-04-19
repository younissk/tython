from pathlib import Path

import pytest

from parser import parse_custom


BASE_DIR = Path(__file__).parent / "cases" / "smoke"


@pytest.mark.smoke
@pytest.mark.parametrize("fixture", sorted((BASE_DIR / "valid").glob("*.dp")))
def test_smoke_valid_custom_syntax_parses(fixture: Path) -> None:
    parse_custom(fixture.read_text())


@pytest.mark.smoke
@pytest.mark.parametrize("fixture", sorted((BASE_DIR / "invalid").glob("*.dp")))
def test_smoke_invalid_custom_syntax_fails(fixture: Path) -> None:
    with pytest.raises(SyntaxError):
        parse_custom(fixture.read_text())
