import ast
from pathlib import Path

import pytest

from parser import lower, parse, parse_custom


BASE_DIR = Path(__file__).parent / "cases" / "differential"
COMPAT_DIR = BASE_DIR / "compat_python"
CUSTOM_DIR = BASE_DIR / "custom_syntax"


@pytest.mark.differential
@pytest.mark.parametrize("fixture", sorted(COMPAT_DIR.glob("*.ty")))
def test_differential_compat_python_matches_cpython(fixture: Path) -> None:
    source = fixture.read_text()

    custom_ast = parse(source, mode="exec")
    cpython_ast = ast.parse(source, mode="exec")

    assert ast.dump(custom_ast, include_attributes=False) == ast.dump(
        cpython_ast, include_attributes=False
    )
    compile(custom_ast, str(fixture), "exec")


def _custom_fixtures() -> list[Path]:
    return sorted(CUSTOM_DIR.glob("*.ty"))


@pytest.mark.differential
@pytest.mark.parametrize("fixture", _custom_fixtures())
def test_differential_custom_syntax_lowers_to_expected_python(fixture: Path) -> None:
    source = fixture.read_text()
    expected_path = fixture.with_suffix(".py")
    expected_source = expected_path.read_text()

    lowered = lower(parse_custom(source))
    expected = ast.parse(expected_source, mode="exec")

    assert ast.dump(lowered, include_attributes=False) == ast.dump(
        expected, include_attributes=False
    )
    compile(lowered, str(fixture), "exec")
