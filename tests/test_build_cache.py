import json
import os
from contextlib import contextmanager
from pathlib import Path

from typer.testing import CliRunner

from parser.cli_typer import app


runner = CliRunner()


@contextmanager
def chdir(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _write_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "my_app"
    (project_root / "src").mkdir(parents=True)
    (project_root / "src" / "main.ty").write_text("print(1 + 1)\n")

    (project_root / "project.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "my_app"',
                'version = "0.1.0"',
                'entry = "src/main.ty"',
                "",
                "[python]",
                "dependencies = [",
                "]",
                "",
            ]
        )
    )
    return project_root


def _build_json(project_root: Path) -> dict[str, object]:
    with chdir(project_root):
        result = runner.invoke(app, ["build", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    return payload


def test_build_cache_hits_on_second_build(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)

    first = _build_json(project_root)
    assert first["compiled"] == 1
    assert first["cache_misses"] == 1
    assert first["cache_hits"] == 0

    second = _build_json(project_root)
    assert second["compiled"] == 0
    assert second["cache_misses"] == 0
    assert second["cache_hits"] == 1


def test_build_cache_misses_when_source_changes(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)
    _build_json(project_root)

    source = project_root / "src" / "main.ty"
    source.write_text('print("changed")\n')

    third = _build_json(project_root)
    assert third["compiled"] == 1
    assert third["cache_misses"] == 1
    assert third["cache_hits"] == 0


def test_build_cache_invalidates_on_lock_change(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)
    _build_json(project_root)
    _build_json(project_root)

    lock_path = project_root / "project.lock"
    assert lock_path.exists()
    lock_path.write_text(lock_path.read_text() + "\n# touch\n")

    after = _build_json(project_root)
    assert after["compiled"] == 1
    assert after["cache_misses"] == 1
    assert after["cache_hits"] == 0

