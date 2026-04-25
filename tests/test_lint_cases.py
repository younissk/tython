from __future__ import annotations

from pathlib import Path

import pytest

from parser.lint import lint_file


BASE_DIR = Path(__file__).parent / "cases" / "lint"


@pytest.mark.parametrize("fixture", sorted((BASE_DIR / "valid").glob("*.ty")))
def test_lint_valid_cases_pass(fixture: Path) -> None:
    assert lint_file(fixture) == []


@pytest.mark.parametrize("fixture", sorted((BASE_DIR / "invalid").glob("*.ty")))
def test_lint_invalid_cases_fail(fixture: Path) -> None:
    assert lint_file(fixture)
