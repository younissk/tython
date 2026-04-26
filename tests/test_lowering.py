import ast
from pathlib import Path

import pytest

from parser import lower, parse_custom


BASE_DIR = Path(__file__).parent / "cases" / "lowering"


@pytest.mark.lowering
@pytest.mark.parametrize("fixture", sorted(BASE_DIR.glob("*.ty")))
def test_lowering_custom_ir_to_python_ast(fixture: Path) -> None:
    source = fixture.read_text()
    expected_source = fixture.with_suffix(".py").read_text()

    lowered = lower(parse_custom(source))
    expected = ast.parse(expected_source, mode="exec")

    assert ast.dump(lowered, include_attributes=False) == ast.dump(
        expected, include_attributes=False
    )
