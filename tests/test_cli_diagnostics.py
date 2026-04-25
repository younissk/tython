import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MAIN_PY), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def _write_project(root: Path, source: str) -> None:
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


def test_invalid_import_form_reports_explicit_error(tmp_path: Path) -> None:
    _write_project(tmp_path, "import requests\n")

    completed = _run_cli("build", cwd=tmp_path)

    assert completed.returncode == 1
    assert "E1028" in completed.stderr
    assert "invalid import form" in completed.stderr


def test_missing_project_manifest_reports_error(tmp_path: Path) -> None:
    completed = _run_cli("build", cwd=tmp_path)

    assert completed.returncode == 1
    assert "project.toml not found" in completed.stderr


def test_missing_pyimport_dependency_has_world_specific_message(tmp_path: Path) -> None:
    _write_project(tmp_path, "pyimport definitely_not_installed_pkg as dep\nprint(dep)\n")

    completed = _run_cli("run", "src/main.ty", cwd=tmp_path)

    assert completed.returncode == 1
    assert "Python dependency error: pyimport 'definitely_not_installed_pkg'" in completed.stderr
    assert "Python dependency world" in completed.stderr


def test_lint_valid_project_succeeds(tmp_path: Path) -> None:
    _write_project(tmp_path, "print(\"ok\")\n")
    (tmp_path / "src" / "extra.ty").write_text("var count = 1\nprint(count)\n")

    completed = _run_cli("lint", cwd=tmp_path)

    assert completed.returncode == 0
    assert "Linted 2 file(s)" in completed.stdout


def test_lint_reports_multiple_failing_files(tmp_path: Path) -> None:
    _write_project(tmp_path, "print(x)\n")
    (tmp_path / "src" / "extra.ty").write_text("var count: int\nprint(count)\n")

    completed = _run_cli("lint", cwd=tmp_path)

    assert completed.returncode == 1
    assert "src/main.ty" in completed.stderr
    assert "src/extra.ty" in completed.stderr
    assert "E2024" in completed.stderr
    assert "E2022" in completed.stderr
