from pathlib import Path

from typer.testing import CliRunner

from parser.cli_typer import app


runner = CliRunner()


def _sample_source() -> str:
    return """\
enum Habitat:
    ocean
    forest

var ocean: Habitat = Habitat.ocean
print(ocean == Habitat.ocean)
"""


def test_run_succeeds_for_txt(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text(_sample_source())

    result = runner.invoke(app, ["run", str(file_path)])

    assert result.exit_code == 0, result.output
    assert "True" in result.output


def test_run_succeeds_for_ty(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.ty"
    file_path.write_text(_sample_source())

    result = runner.invoke(app, ["run", str(file_path)])

    assert result.exit_code == 0, result.output
    assert "True" in result.output


def test_transpile_succeeds_for_txt(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.txt"
    output_path = tmp_path / "sample.py"
    input_path.write_text(_sample_source())

    result = runner.invoke(
        app,
        ["transpile", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    generated = output_path.read_text()
    assert "from enum import Enum" in generated
    assert "class Habitat(Enum):" in generated


def test_transpile_succeeds_for_ty(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.ty"
    output_path = tmp_path / "sample.py"
    input_path.write_text(_sample_source())

    result = runner.invoke(
        app,
        ["transpile", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    generated = output_path.read_text()
    assert "from enum import Enum" in generated
    assert "class Habitat(Enum):" in generated


def test_run_rejects_invalid_extension(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text("print('hello')\n")

    result = runner.invoke(app, ["run", str(file_path)])

    assert result.exit_code != 0
    assert "Unsupported input extension" in result.output
    assert "Only .txt and .ty files are supported." in result.output


def test_run_rejects_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.ty"

    result = runner.invoke(app, ["run", str(missing_path)])

    assert result.exit_code != 0
    assert "Input file not found" in result.output


def test_help_and_version() -> None:
    help_result = runner.invoke(app, ["--help"])
    version_result = runner.invoke(app, ["--version"])

    assert help_result.exit_code == 0
    assert "run" in help_result.output
    assert "transpile" in help_result.output
    assert "repl" in help_result.output
    assert "version" in help_result.output
    assert "lsp" in help_result.output

    assert version_result.exit_code == 0
    assert "tython" in version_result.output


def test_lsp_install_vim_writes_plugin_files(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"

    result = runner.invoke(
        app,
        [
            "lsp",
            "install",
            "vim",
            "--vim-pack-root",
            str(pack_root),
            "--no-install-lsp-plugin",
        ],
    )

    assert result.exit_code == 0, result.output
    plugin_root = pack_root / "tython" / "start" / "tython-vim"
    assert (plugin_root / "ftdetect" / "tython.vim").exists()
    assert (plugin_root / "plugin" / "tython_lsp.vim").exists()
    assert (plugin_root / "syntax" / "tython.vim").exists()

    plugin_text = (plugin_root / "plugin" / "tython_lsp.vim").read_text()
    assert "LspAddServer" in plugin_text
    assert "'tython', 'lsp', 'start'" in plugin_text
