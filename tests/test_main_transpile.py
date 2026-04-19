import subprocess
import sys
import ast
from pathlib import Path


def test_main_transpiles_txt_to_python_file(tmp_path: Path) -> None:
    source = """\
enum Habitat:
    ocean
    forest

var ocean: Habitat = Habitat.ocean
print(ocean == Habitat.ocean)
"""
    input_path = tmp_path / "sample.txt"
    output_path = tmp_path / "sample.py"
    input_path.write_text(source)

    completed = subprocess.run(
        [
            sys.executable,
            "main.py",
            str(input_path),
            "--transpile",
            "-o",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.exists()

    generated = output_path.read_text()
    assert "from enum import Enum" in generated
    assert "class Habitat(Enum):" in generated
    generated_ast = ast.parse(generated, mode="exec")
    assert "ocean = 'ocean'" in ast.unparse(generated_ast)
    assert "forest = 'forest'" in ast.unparse(generated_ast)


def test_main_transpiles_txt_with_bom(tmp_path: Path) -> None:
    source = "\ufeffenum Habitat:\n    ocean\n    forest\n"
    input_path = tmp_path / "bom_sample.txt"
    output_path = tmp_path / "bom_sample.py"
    input_path.write_text(source, encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "main.py",
            str(input_path),
            "--transpile",
            "-o",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.exists()
