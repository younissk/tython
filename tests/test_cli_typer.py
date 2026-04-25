import shutil
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
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

    lines = [
        "[project]",
        'name = "my_app"',
        'version = "0.1.0"',
        'entry = "src/main.ty"',
        "",
    ]
    lines.extend(
        [
            "[python]",
            "dependencies = [",
            "]",
            "",
        ]
    )
    (project_root / "project.toml").write_text("\n".join(lines))
    return project_root


def test_init_creates_minimal_project(tmp_path: Path) -> None:
    project_root = tmp_path / "new_app"
    project_root.mkdir()
    with chdir(project_root):
        result = runner.invoke(app, ["init", "--name", "new_app"])

    assert result.exit_code == 0, result.output
    assert (project_root / "project.toml").exists()
    assert (project_root / "src" / "main.ty").exists()
    assert (project_root / ".tython" / "build").exists()
    assert (project_root / ".tython" / "cache").exists()

    manifest = (project_root / "project.toml").read_text()
    assert 'name = "new_app"' in manifest
    assert 'entry = "src/main.ty"' in manifest
    assert (
        project_root / "src" / "main.ty"
    ).read_text() == 'print("hello from tython")\n'


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=path, check=True
    )


def _create_native_dep_repo(tmp_path: Path) -> Path:
    dep_root = tmp_path / "http_dep"
    (dep_root / "src").mkdir(parents=True)
    (dep_root / "src" / "client.ty").write_text("func get() -> int:\n    return 1\n")
    _init_git_repo(dep_root)
    subprocess.run(["git", "add", "."], cwd=dep_root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=dep_root, check=True)
    return dep_root


def _head_commit(path: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def test_build_generates_python_project(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)

    with chdir(project_root):
        result = runner.invoke(app, ["build"])

    assert result.exit_code == 0, result.output

    build_root = project_root / ".tython" / "build"
    assert (build_root / "pyproject.toml").exists()
    assert (build_root / "src" / "my_app" / "main.py").exists()


def test_add_py_dependency_updates_manifest(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)

    with chdir(project_root):
        result = runner.invoke(app, ["add", "requests>=2.32", "--py"])

    assert result.exit_code == 0, result.output
    text = (project_root / "project.toml").read_text()
    assert '"requests>=2.32"' in text


def test_lock_writes_exact_commit_for_native_package(tmp_path: Path) -> None:
    dep_root = _create_native_dep_repo(tmp_path)
    commit = _head_commit(dep_root)
    project_root = _write_project(tmp_path)
    with chdir(project_root):
        add_result = runner.invoke(
            app, ["add", str(dep_root), "--rev", commit, "--name", "http"]
        )
    assert add_result.exit_code == 0, add_result.output

    with chdir(project_root):
        result = runner.invoke(app, ["lock"])

    assert result.exit_code == 0, result.output

    lock_path = project_root / "project.lock"
    assert lock_path.exists()
    lock_text = lock_path.read_text()
    assert "[packages.http]" in lock_text
    assert "commit =" in lock_text


def test_run_path_target_executes_project_file(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)

    with chdir(project_root):
        result = runner.invoke(app, ["run", "src/main.ty"])

    assert result.exit_code == 0, result.output
    assert "2" in result.output


def test_run_without_target_uses_project_entry(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)

    with chdir(project_root):
        result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert "2" in result.output


def test_help_and_version() -> None:
    help_result = runner.invoke(app, ["--help"])
    lsp_help_result = runner.invoke(app, ["lsp", "install", "--help"])
    version_result = runner.invoke(app, ["--version"])

    assert help_result.exit_code == 0
    assert "add" in help_result.output
    assert "lock" in help_result.output
    assert "build" in help_result.output
    assert "format" in help_result.output
    assert "run" in help_result.output
    assert "lsp" in help_result.output
    assert "nvim" in lsp_help_result.output

    assert version_result.exit_code == 0
    assert "tython" in version_result.output


def test_format_normalizes_project_sources(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)
    source_path = project_root / "src" / "main.ty"
    source_path.write_text("print( 1 + 1 )\n")

    with chdir(project_root):
        result = runner.invoke(app, ["format"])

    assert result.exit_code == 0, result.output
    assert source_path.read_text() == "print(1 + 1)\n"


def test_format_is_idempotent(tmp_path: Path) -> None:
    project_root = _write_project(tmp_path)

    with chdir(project_root):
        first = runner.invoke(app, ["format"])
        second = runner.invoke(app, ["format"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert "Formatted" in second.output


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
    assert (plugin_root / "plugin" / "tython_lsp.lua").exists()
    assert (plugin_root / "syntax" / "tython.vim").exists()
    assert (plugin_root / "lsp" / "tython.lua").exists()

    plugin_text = (plugin_root / "plugin" / "tython_lsp.vim").read_text()
    assert "LspAddServer" in plugin_text
    assert "'tython', 'lsp', 'start'" in plugin_text


def test_lsp_install_nvim_writes_plugin_files(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"

    result = runner.invoke(
        app,
        [
            "lsp",
            "install",
            "nvim",
            "--nvim-pack-root",
            str(pack_root),
        ],
    )

    assert result.exit_code == 0, result.output
    plugin_root = pack_root / "tython" / "start" / "tython-vim"
    assert (plugin_root / "ftdetect" / "tython.vim").exists()
    assert (plugin_root / "plugin" / "tython_lsp.vim").exists()
    assert (plugin_root / "plugin" / "tython_lsp.lua").exists()
    assert (plugin_root / "syntax" / "tython.vim").exists()
    assert (plugin_root / "lsp" / "tython.lua").exists()

    plugin_text = (plugin_root / "plugin" / "tython_lsp.lua").read_text()
    assert "vim.lsp.enable('tython')" in plugin_text
    config_text = (plugin_root / "lsp" / "tython.lua").read_text()
    assert "root_markers = { 'project.toml', '.git' }" in config_text


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_nvim_headless_attaches_tython_lsp(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    uv_bin = shutil.which("uv")
    assert uv_bin is not None

    project_root = _write_project(tmp_path)
    source_path = project_root / "src" / "main.ty"
    source_path.write_text("const value: int = 1\n")

    pack_root = tmp_path / "pack"
    install_result = runner.invoke(
        app,
        [
            "lsp",
            "install",
            "nvim",
            "--nvim-pack-root",
            str(pack_root),
        ],
    )
    assert install_result.exit_code == 0, install_result.output

    init_path = tmp_path / "init.lua"
    init_path.write_text(
        """
vim.g.tython_lsp_cmd = {{ {uv!r}, 'run', 'tython-lsp' }}
vim.opt.runtimepath:prepend({package_root!r})
vim.cmd('source ' .. vim.fn.fnameescape({ftdetect!r}))
vim.cmd('luafile ' .. vim.fn.fnameescape({plugin!r}))
vim.cmd('filetype plugin on')
local attached = false
vim.api.nvim_create_autocmd('LspAttach', {{
  callback = function(args)
    if args.buf == vim.api.nvim_get_current_buf() then
      attached = true
    end
  end,
}})
vim.cmd('edit ' .. vim.fn.fnameescape({source!r}))
vim.wait(10000, function()
  return attached
end, 50)
assert(attached, 'tython lsp did not attach')
local client_attached = false
for _, client in ipairs(vim.lsp.get_clients({{ bufnr = 0 }})) do
  if client.name == 'tython' then
    client_attached = true
    break
  end
end
assert(client_attached, 'tython client missing')
assert(vim.bo.filetype == 'tython', 'unexpected filetype: ' .. vim.bo.filetype)
vim.cmd('qa!')
""".format(
            uv=uv_bin,
            package_root=str(pack_root / "tython" / "start" / "tython-vim"),
            ftdetect=str(
                pack_root
                / "tython"
                / "start"
                / "tython-vim"
                / "ftdetect"
                / "tython.vim"
            ),
            plugin=str(
                pack_root
                / "tython"
                / "start"
                / "tython-vim"
                / "plugin"
                / "tython_lsp.lua"
            ),
            source=str(source_path),
        )
    )

    completed = subprocess.run(
        ["nvim", "--headless", "-u", str(init_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
