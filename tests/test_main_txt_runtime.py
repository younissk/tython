import subprocess
import sys
from pathlib import Path


def test_main_executes_txt_custom_enum(tmp_path: Path) -> None:
    source = """\
enum Habitat:
    ocean
    forest

var ocean: Habitat = Habitat.ocean
print(ocean == Habitat.ocean)
"""
    file_path = tmp_path / "sample.txt"
    file_path.write_text(source)

    completed = subprocess.run(
        [sys.executable, "main.py", str(file_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "True"
