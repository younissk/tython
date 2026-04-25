import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_transpile_accepts_ty_sources(tmp_path: Path) -> None:
    input_path = tmp_path / "input.ty"
    output_path = tmp_path / "output.py"
    input_path.write_text("print(40 + 2)\n")

    completed = subprocess.run(
        [sys.executable, "-m", "parser.transpile", str(input_path), str(output_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.read_text() == "print(40 + 2)\n"
    assert output_path.as_posix() in completed.stdout


def test_transpile_rejects_txt_sources(tmp_path: Path) -> None:
    input_path = tmp_path / "input.txt"
    output_path = tmp_path / "output.py"
    input_path.write_text("print(40 + 2)\n")

    completed = subprocess.run(
        [sys.executable, "-m", "parser.transpile", str(input_path), str(output_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert ".ty inputs only" in completed.stderr
