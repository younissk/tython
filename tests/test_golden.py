import ast
import re
from pathlib import Path

import pytest

from parser import parse_custom


BASE_DIR = Path(__file__).parent / "cases" / "golden"
_EMPTY_LIST_FIELD_RE = re.compile(r"^\s+[A-Za-z_][A-Za-z0-9_]*=\[\][,)]*$")


def _normalize_snapshot(snapshot: str) -> str:
    lines = [
        line for line in snapshot.splitlines() if not _EMPTY_LIST_FIELD_RE.match(line)
    ]
    return "\n".join(lines)


@pytest.mark.golden
@pytest.mark.parametrize("fixture", sorted(BASE_DIR.glob("*.ty")))
def test_golden_parse_custom_ast_snapshot(fixture: Path) -> None:
    tree = parse_custom(fixture.read_text())
    snapshot_path = fixture.with_suffix(".ast")
    snapshot = _normalize_snapshot(ast.dump(tree, include_attributes=False, indent=2))

    if not snapshot_path.exists():
        snapshot_path.write_text(snapshot + "\n")

    assert snapshot == snapshot_path.read_text().rstrip("\n")
