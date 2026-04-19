from pathlib import Path

import pytest

from parser import parse_custom


BASE_DIR = Path(__file__).parent / "cases" / "smoke"


def _fixtures(layer: str) -> list[Path]:
    path = BASE_DIR / layer
    return sorted([*path.glob("*.dp"), *path.glob("*.ty")])


@pytest.mark.smoke
@pytest.mark.parametrize("fixture", _fixtures("valid"))
def test_smoke_valid_custom_syntax_parses(fixture: Path) -> None:
    parse_custom(fixture.read_text())


@pytest.mark.smoke
@pytest.mark.parametrize("fixture", _fixtures("invalid"))
def test_smoke_invalid_custom_syntax_fails(fixture: Path) -> None:
    with pytest.raises(SyntaxError):
        parse_custom(fixture.read_text())
