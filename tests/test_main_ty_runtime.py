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


def _write_project_with_python_deps(
    tmp_path: Path, source: str, *, python_deps: list[str]
) -> Path:
    root = tmp_path / "my_app"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.ty").write_text(source)
    deps = "\n".join(f'  "{dep}",' for dep in python_deps)
    (root / "project.toml").write_text(
        f"""
[project]
name = "my_app"
version = "0.1.0"
entry = "src/main.ty"

[python]
dependencies = [
{deps}
]
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


def test_run_syncs_python_deps_and_executes_pyimport(tmp_path: Path) -> None:
    project_root = tmp_path / "my_app"
    localpkg_root = project_root / "pydeps" / "localpkg"
    (localpkg_root / "localpkg").mkdir(parents=True)
    (localpkg_root / "localpkg" / "__init__.py").write_text(
        "def answer() -> int:\n    return 42\n"
    )
    (localpkg_root / "setup.py").write_text(
        """
from setuptools import setup

setup(
    name="localpkg",
    version="0.0.0",
    packages=["localpkg"],
)
""".strip()
        + "\n"
    )

    project_root = _write_project_with_python_deps(
        tmp_path,
        "pyimport localpkg as lp\nprint(lp.answer())\n",
        python_deps=["./pydeps/localpkg"],
    )

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "run", "src/main.ty"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "42"
    assert (project_root / ".tython" / "python" / ".venv").exists()


def test_pyimport_stub_influences_typechecking_in_lint(tmp_path: Path) -> None:
    project_root = _write_project(
        tmp_path,
        "pyimport localpkg as lp\nvar x: int = lp.answer()\nprint(x)\n",
    )
    (project_root / "stubs").mkdir(parents=True)
    (project_root / "stubs" / "localpkg.pyi").write_text(
        "def answer() -> int: ...\n"
    )

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "lint"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    # negative case
    (project_root / "src" / "main.ty").write_text(
        "pyimport localpkg as lp\nvar x: str = lp.answer()\nprint(x)\n"
    )
    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "lint"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "E2016" in completed.stderr


def test_file_import_exposes_class_member_types_across_modules(tmp_path: Path) -> None:
    project_root = tmp_path / "my_app"
    (project_root / "src").mkdir(parents=True)
    (project_root / "src" / "ols.ty").write_text(
        """
record Model {
    fit: (X: Matrix,y: Matrix) -> Matrix
}

class OLS is Model {
    pub var beta: Matrix

    pub func fit(X: Matrix,y: Matrix) -> Matrix {
        this.beta = (X.transpose()@X).inverse()@X.transpose()@y
        return this.beta
    }
}
""".strip()
        + "\n"
    )
    (project_root / "src" / "main.ty").write_text(
        """
import "./ols.ty" as OLS

const X = Matrix([[1],[4],[7]])
const Y = Matrix([[3],[6],[8]])

const MODEL = OLS.OLS()
MODEL.fit(X: X, y: Y)

var yhat = X @ MODEL.beta
print(yhat)
""".strip()
        + "\n"
    )
    (project_root / "project.toml").write_text(
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

    completed = subprocess.run(
        [sys.executable, str(MAIN_PY), "lint"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
