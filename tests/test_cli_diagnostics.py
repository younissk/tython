import json
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


def test_cli_json_renderer_emits_structured_diagnostic(tmp_path: Path) -> None:
    source = "var value\n"
    file_path = tmp_path / "invalid.txt"
    file_path.write_text(source)

    completed = _run_cli(str(file_path), "--errors", "json", cwd=tmp_path)

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    for required in ["code", "severity", "phase", "message", "file", "range", "timestamp"]:
        assert required in payload
    assert payload["severity"] == "error"


def test_cli_jsonl_export_writes_file(tmp_path: Path) -> None:
    source = "var value\n"
    file_path = tmp_path / "invalid.txt"
    export_path = tmp_path / "diag.jsonl"
    file_path.write_text(source)

    completed = _run_cli(
        str(file_path),
        "--errors",
        "jsonl",
        "--export-errors",
        str(export_path),
        cwd=tmp_path,
    )

    assert completed.returncode == 1
    assert export_path.exists()
    exported = json.loads(export_path.read_text().strip())
    assert exported["code"].startswith("E")


def test_cli_runtime_exception_maps_to_panic_diagnostic(tmp_path: Path) -> None:
    source = "var x = 1 / 0\n"
    file_path = tmp_path / "runtime_panic.txt"
    export_path = tmp_path / "runtime.jsonl"
    file_path.write_text(source)

    completed = _run_cli(
        str(file_path),
        "--errors",
        "compact",
        "--export-errors",
        str(export_path),
        cwd=tmp_path,
    )

    assert completed.returncode == 1
    assert "internal[P0001]" in completed.stdout

    exported = json.loads(export_path.read_text().strip())
    assert exported["code"] == "P0001"
    assert exported["phase"] == "panic"
