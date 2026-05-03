from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import shutil
import sys
import tempfile
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .core import lower
from .custom_frontend import (
    FILE_IMPORT_SENTINEL,
    NATIVE_IMPORT_SENTINEL,
    PYIMPORT_SENTINEL,
    parse_custom_source,
)
from .project import (
    LOCK_FILE,
    ProjectManifest,
    ensure_cache_dirs,
    load_manifest,
    resolve_lock,
    write_lock,
)
from .semantics import analyze_semantics


@dataclass(frozen=True)
class SourceUnit:
    source_path: Path
    module_name: str
    source_root: Path


@dataclass
class BuildReport:
    compiled: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    stale_outputs_removed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "compiled": self.compiled,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "stale_outputs_removed": self.stale_outputs_removed,
        }


def lock_project(project_root: Path):
    manifest = load_manifest(project_root)
    lock = resolve_lock(manifest)
    write_lock(project_root, lock)
    return lock


def build_project(
    project_root: Path,
    *,
    report: BuildReport | None = None,
) -> Path:
    manifest = load_manifest(project_root)
    from .project import load_lock

    lock = load_lock(project_root)
    if lock is None:
        lock = lock_project(project_root)

    cache_root, build_root = ensure_cache_dirs(project_root)
    build_root.mkdir(parents=True, exist_ok=True)

    build_report = report if report is not None else BuildReport()

    units = _collect_units(project_root, manifest)
    module_index = {unit.source_path.resolve(): unit.module_name for unit in units}
    module_graph_hash = _module_graph_hash(project_root, units)
    lock_hash = _build_lock_hash(project_root)
    python_version = _python_version()
    tython_version = _tython_version()

    expected_outputs: set[Path] = set()

    for unit in units:
        source = unit.source_path.read_text()
        source = _normalize_source(source)

        native_import_map: dict[str, str] = {}
        file_import_map: dict[str, str] = {}
        for kind, raw, _alias in _scan_imports_from_source(source):
            if kind == "native":
                native_import_map[raw] = _resolve_native_import(
                    raw=raw,
                    manifest=manifest,
                    module_index=module_index,
                )
            elif kind == "file":
                resolved_path = _resolve_file_path(unit.source_path, raw)
                module = module_index.get(resolved_path)
                if module is None:
                    raise SyntaxError(
                        f"[E3202] Line 1: unresolved file import '{raw}'. Hint: ensure imported .ty file exists in build graph."
                    )
                file_import_map[raw] = module

        output_path = _module_to_file(build_root, unit.module_name)
        expected_outputs.add(output_path.resolve())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_package_inits(output_path.parent, build_root / "src")

        import_maps_hash = _import_maps_hash(
            native_import_map=native_import_map,
            file_import_map=file_import_map,
        )
        cache_key = _artifact_cache_key(
            source_bytes=source.encode("utf-8"),
            tython_version=tython_version,
            python_version=python_version,
            lock_hash=lock_hash,
            module_graph_hash=module_graph_hash,
            import_maps_hash=import_maps_hash,
        )
        artifact = _artifact_path(cache_root, cache_key)
        if artifact.exists():
            build_report.cache_hits += 1
            _atomic_write_text(output_path, artifact.read_text(encoding="utf-8"))
            continue

        build_report.cache_misses += 1
        build_report.compiled += 1

        tree = parse_custom_source(source).tree
        analysis = analyze_semantics(
            tree, project_root=project_root, source_path=unit.source_path
        )
        lowered = lower(
            tree,
            native_import_map=native_import_map,
            file_import_map=file_import_map,
            type_context=analysis.type_context,
        )
        rendered = ast.unparse(lowered) + "\n"

        artifact.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(artifact, rendered)
        _atomic_write_text(output_path, rendered)

    build_report.stale_outputs_removed += _remove_stale_outputs(
        build_root=build_root,
        package_name=manifest.name,
        expected_outputs=expected_outputs,
    )

    _copy_runtime_stdlib(build_root)
    _write_generated_pyproject(project_root, manifest, build_root)

    return build_root


def run_generated_target(
    project_root: Path, target_file: Path, *, mode: str = "exec", sync: bool = True
) -> None:
    build_root = build_project(project_root)
    manifest = load_manifest(project_root)
    rel = target_file.resolve().relative_to((project_root / "src").resolve())
    module = rel.with_suffix("").as_posix().replace("/", ".")
    generated = build_root / "src" / manifest.name / (module.replace(".", "/") + ".py")
    if not generated.exists():
        raise SyntaxError(
            f"[E3203] Line 1: target '{target_file}' not in build output. Hint: check file path under src/."
        )

    venv_python: Path | None = None
    wants_env = bool(manifest.python_dependencies) or bool(manifest.python_imports)
    if (sync and wants_env) or _python_venv_dir(project_root).exists():
        venv_python = ensure_python_env(project_root, sync=sync and wants_env)

    runner = _runner_source(
        generated=generated, build_src=build_root / "src", mode=mode
    )
    completed = subprocess.run(
        [str(venv_python) if venv_python is not None else sys.executable, "-c", runner],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode == 0:
        return

    missing = _extract_missing_module(completed.stderr)
    if missing is not None:
        root = missing.split(".", 1)[0]
        suggestion = None
        spec = manifest.python_imports.get(root)
        if spec is not None and spec.distribution:
            suggestion = spec.distribution
        raise RuntimeError(
            "Python dependency error: pyimport "
            f"'{root}' could not be resolved.\n\n"
            "This import belongs to Python dependency world, not native Tython packages.\n\n"
            "Fix:\n"
            f"- add it under [python].dependencies in project.toml{_format_distribution_hint(suggestion)}\n"
            "- run `tython python sync` (or rerun without --no-sync)\n"
            "- rebuild generated Python project"
        )

    raise RuntimeError(completed.stderr.strip() or "Execution failed.")


def ensure_python_env(project_root: Path, *, sync: bool) -> Path:
    """Ensure project-local venv exists, optionally syncing deps. Returns venv python."""
    python_root = project_root / ".tython" / "python"
    python_root.mkdir(parents=True, exist_ok=True)
    venv_dir = _python_venv_dir(project_root)
    venv_python = _venv_python(venv_dir)

    if not venv_python.exists():
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )

    if not sync:
        return venv_python

    manifest = load_manifest(project_root)
    deps = list(manifest.python_dependencies)
    if not deps:
        return venv_python

    fingerprint_path = python_root / "deps.sha256"
    next_fingerprint = _deps_fingerprint(deps)
    if fingerprint_path.exists() and fingerprint_path.read_text().strip() == next_fingerprint:
        return venv_python

    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", *deps],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    fingerprint_path.write_text(next_fingerprint + "\n")
    return venv_python


def _collect_units(project_root: Path, manifest: ProjectManifest) -> list[SourceUnit]:
    units: list[SourceUnit] = []
    src_root = project_root / "src"
    if not src_root.exists():
        raise SyntaxError(
            "[E3204] Line 1: src/ directory missing. Hint: create src/ with .ty sources."
        )

    for path in sorted(src_root.rglob("*.ty")):
        rel_module = (
            path.relative_to(src_root).with_suffix("").as_posix().replace("/", ".")
        )
        module_name = f"{manifest.name}.{rel_module}"
        units.append(
            SourceUnit(
                source_path=path.resolve(),
                module_name=module_name,
                source_root=src_root.resolve(),
            )
        )

    return units


def _collect_imports(tree: ast.AST) -> list[tuple[str, str, str | None]]:
    imports: list[tuple[str, str, str | None]] = []
    if not isinstance(tree, ast.Module):
        return imports
    for stmt in tree.body:
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and len(stmt.value.args) == 2
        ):
            continue
        call = stmt.value
        if not isinstance(call.args[0], ast.Constant) or not isinstance(
            call.args[0].value, str
        ):
            continue
        alias: str | None = None
        if isinstance(call.args[1], ast.Constant) and (
            call.args[1].value is None or isinstance(call.args[1].value, str)
        ):
            alias = call.args[1].value

        if call.func.id == NATIVE_IMPORT_SENTINEL:
            imports.append(("native", call.args[0].value, alias))
        elif call.func.id == FILE_IMPORT_SENTINEL:
            imports.append(("file", call.args[0].value, alias))
        elif call.func.id == PYIMPORT_SENTINEL:
            imports.append(("pyimport", call.args[0].value, alias))
    return imports


def _resolve_native_import(
    *,
    raw: str,
    manifest: ProjectManifest,
    module_index: dict[Path, str],
) -> str:
    local_candidate = f"{manifest.name}.{raw.replace('/', '.')}"
    if local_candidate in module_index.values():
        return local_candidate

    raise SyntaxError(
        f"[E3201] Line 1: unresolved native import '{raw}'. Hint: define matching local module under src/."
    )


def _resolve_file_path(current_file: Path, raw: str) -> Path:
    if not (raw.startswith("./") or raw.startswith("../")):
        raise SyntaxError(
            f"[E3205] Line 1: invalid file import '{raw}'. Hint: file imports must start with ./ or ../."
        )
    return (current_file.parent / raw).resolve()


def _module_to_file(build_root: Path, module: str) -> Path:
    src_root = build_root / "src"
    return src_root / (module.replace(".", "/") + ".py")


def _ensure_package_inits(directory: Path, src_root: Path) -> None:
    current = directory
    while src_root in current.parents or current == src_root:
        init_path = current / "__init__.py"
        if not init_path.exists():
            init_path.write_text("\n")
        if current == src_root:
            break
        current = current.parent


def _write_generated_pyproject(
    project_root: Path, manifest: ProjectManifest, build_root: Path
) -> None:
    lines = [
        "[project]",
        f'name = "{manifest.name}"',
        f'version = "{manifest.version}"',
        'description = "Generated by tython build"',
        'requires-python = ">=3.11"',
        "dependencies = [",
    ]
    for dep in manifest.python_dependencies:
        lines.append(f'  "{dep}",')
    lines.extend(
        [
            "]",
            "",
            "[build-system]",
            'requires = ["setuptools>=69"]',
            'build-backend = "setuptools.build_meta"',
            "",
            "[tool.setuptools.packages.find]",
            'where = ["src"]',
        ]
    )
    (build_root / "pyproject.toml").write_text("\n".join(lines) + "\n")

    if not (build_root / LOCK_FILE).exists() and (project_root / LOCK_FILE).exists():
        shutil.copyfile(project_root / LOCK_FILE, build_root / LOCK_FILE)

def _remove_stale_outputs(
    *,
    build_root: Path,
    package_name: str,
    expected_outputs: set[Path],
) -> int:
    removed = 0
    pkg_root = (build_root / "src" / package_name).resolve()
    if not pkg_root.exists():
        return 0

    for path in pkg_root.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        if path.resolve() not in expected_outputs:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def _copy_runtime_stdlib(build_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "tython_std"
    if not src.exists():
        return
    dest = build_root / "src" / "tython_std"
    shutil.copytree(src, dest, dirs_exist_ok=True)


def _python_venv_dir(project_root: Path) -> Path:
    return project_root / ".tython" / "python" / ".venv"


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _deps_fingerprint(deps: list[str]) -> str:
    blob = "\n".join(deps).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


_MISSING_SENTINEL = "__TYTHON_MISSING_PYMODULE__="


def _runner_source(*, generated: Path, build_src: Path, mode: str) -> str:
    # IMPORTANT: keep this as plain Python source; it runs in a subprocess.
    gen = str(generated)
    bsrc = str(build_src)
    return "\n".join(
        [
            "import sys",
            f"build_src = {bsrc!r}",
            "if build_src not in sys.path:",
            "    sys.path.insert(0, build_src)",
            f"generated = {gen!r}",
            f"mode = {mode!r}",
            "try:",
            "    source = open(generated, 'r', encoding='utf-8').read()",
            "    if mode == 'eval':",
            "        code = compile(source, generated, 'eval')",
            "        result = eval(code, {'__name__': '__main__'})",
            "        if result is not None:",
            "            print(result)",
            "    else:",
            "        code = compile(source, generated, mode)",
            "        exec(code, {'__name__': '__main__'})",
            "except ModuleNotFoundError as exc:",
            "    name = getattr(exc, 'name', None) or 'unknown'",
            f"    sys.stderr.write({(_MISSING_SENTINEL)!r} + str(name) + '\\n')",
            "    raise",
        ]
    )


def _extract_missing_module(stderr: str) -> str | None:
    for line in stderr.splitlines():
        if line.startswith(_MISSING_SENTINEL):
            return line.split("=", 1)[-1].strip() or None
    return None


def _format_distribution_hint(distribution: str | None) -> str:
    if not distribution:
        return ""
    # Keep it short; this is appended to the bullet line.
    return f" (try: {distribution})"


def _normalize_source(source: str) -> str:
    if source.startswith("\ufeff"):
        return source.removeprefix("\ufeff")
    return source


_CACHE_SCHEMA_VERSION = "tython-cache-v1"


def _python_version() -> str:
    info = sys.version_info
    return f"{info.major}.{info.minor}.{info.micro}"


def _tython_version() -> str:
    try:
        return version("tython")
    except PackageNotFoundError:
        return "0.1.0"


def _build_lock_hash(project_root: Path) -> str:
    lock_path = project_root / LOCK_FILE
    if lock_path.exists():
        blob = lock_path.read_bytes()
    else:
        blob = (project_root / "project.toml").read_bytes()
    return hashlib.sha256(blob).hexdigest()


def _module_graph_hash(project_root: Path, units: list[SourceUnit]) -> str:
    src_root = (project_root / "src").resolve()
    rels = sorted(
        unit.source_path.resolve().relative_to(src_root).as_posix() for unit in units
    )
    return hashlib.sha256("\n".join(rels).encode("utf-8")).hexdigest()


def _import_maps_hash(*, native_import_map: dict[str, str], file_import_map: dict[str, str]) -> str:
    payload = json.dumps(
        {"native": native_import_map, "file": file_import_map},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _artifact_cache_key(
    *,
    source_bytes: bytes,
    tython_version: str,
    python_version: str,
    lock_hash: str,
    module_graph_hash: str,
    import_maps_hash: str,
) -> str:
    h = hashlib.sha256()
    h.update(b"schema=" + _CACHE_SCHEMA_VERSION.encode("utf-8") + b"\0")
    h.update(b"tython=" + tython_version.encode("utf-8") + b"\0")
    h.update(b"python=" + python_version.encode("utf-8") + b"\0")
    h.update(b"lock=" + lock_hash.encode("utf-8") + b"\0")
    h.update(b"graph=" + module_graph_hash.encode("utf-8") + b"\0")
    h.update(b"imports=" + import_maps_hash.encode("utf-8") + b"\0")
    h.update(b"source\0")
    h.update(source_bytes)
    return h.hexdigest()


def _artifact_path(cache_root: Path, cache_key: str) -> Path:
    return cache_root / "artifacts" / "py" / cache_key[:2] / f"{cache_key}.py"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


_PYIMPORT_SCAN_RE = re.compile(
    r"^(?P<indent>[ \t]*)pyimport[ \t]+(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?[ \t]*$"
)
_FILE_IMPORT_SCAN_RE = re.compile(
    r"^(?P<indent>[ \t]*)import[ \t]+(?P<quote>['\"])(?P<path>.+?)(?P=quote)[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
)
_NATIVE_IMPORT_SCAN_RE = re.compile(
    r"^(?P<indent>[ \t]*)import[ \t]+(?P<target>[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)+)[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)[ \t]*$"
)


def _scan_imports_from_source(source: str) -> list[tuple[str, str, str | None]]:
    imports: list[tuple[str, str, str | None]] = []
    for line in source.splitlines():
        code, _sep, _comment = line.partition("#")
        stripped = code.strip()
        if stripped == "":
            continue

        py_match = _PYIMPORT_SCAN_RE.match(code)
        if py_match is not None:
            module = py_match.group("module")
            alias = py_match.group("alias")
            imports.append(("pyimport", module, alias))
            continue

        file_match = _FILE_IMPORT_SCAN_RE.match(code)
        if file_match is not None:
            path = file_match.group("path")
            alias = file_match.group("alias")
            imports.append(("file", path, alias))
            continue

        native_match = _NATIVE_IMPORT_SCAN_RE.match(code)
        if native_match is not None:
            target = native_match.group("target")
            alias = native_match.group("alias")
            imports.append(("native", target, alias))
            continue

    return imports
