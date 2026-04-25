import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"


def _write_project(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "my_app"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.ty").write_text(source)
    (root / "project.toml").write_text(
        """
[project]
name = "my_app"
version = "0.1.0"
entry = "src/main.ty"

[python]
dependencies = []
""".strip()
        + "\n"
    )
    return root


def test_main_executes_project_path_target(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path, "print(40 + 2)\n")

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "run", "src/main.ty"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "42"


def test_main_executes_matrix_project_target(tmp_path: Path) -> None:
    project_root = _write_project(
        tmp_path,
        """
var a = Matrix([[1, 2], [3, 4]])
print(a.sum())
print(a.transpose()[0, 1])
""".strip()
        + "\n",
    )

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "run", "src/main.ty"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().splitlines() == ["10", "3"]


def test_main_matrix_metadata_contract(tmp_path: Path) -> None:
    project_root = _write_project(
        tmp_path,
        """
var a = Matrix([[1, 2], [3, 4]])
var b = Matrix([[1.0, 2.0], [3.0, 4.0]])
print(a.shape)
print(a.dtype)
print(b.dtype)
""".strip()
        + "\n",
    )

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "run", "src/main.ty"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().splitlines() == ["[2, 2]", "int", "float"]
