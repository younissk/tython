import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"


def _write_project(tmp_path: Path) -> Path:
    root = tmp_path / "my_app"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.ty").write_text("print(1)\n")
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


def test_main_build_generates_python_project(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "build"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (project_root / ".tython" / "build" / "pyproject.toml").exists()
    assert (project_root / ".tython" / "build" / "src" / "my_app" / "main.py").exists()
