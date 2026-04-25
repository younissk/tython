import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"


def _write_project(tmp_path: Path) -> Path:
    root = tmp_path / "my_app"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.ty").write_text("print(40 + 2)\n")
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
    project_root = _write_project(tmp_path)

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "run", "src/main.ty"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "42"
