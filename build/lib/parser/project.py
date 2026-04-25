from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_FILE = "project.toml"
LOCK_FILE = "project.lock"
CACHE_DIR = ".tython/cache"
BUILD_DIR = ".tython/build"

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PY_IMPORT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


@dataclass(frozen=True)
class PackageSpec:
    name: str
    git: str
    requested: str


@dataclass(frozen=True)
class LockedPackage:
    name: str
    git: str
    requested: str
    commit: str
    resolved_version: str


@dataclass(frozen=True)
class ProjectManifest:
    name: str
    version: str
    entry: str
    packages: dict[str, PackageSpec] = field(default_factory=dict)
    python_dependencies: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectLock:
    packages: dict[str, LockedPackage] = field(default_factory=dict)
    python_dependencies: list[str] = field(default_factory=list)


def is_path_target(target: str) -> bool:
    return (
        target.startswith("./")
        or target.startswith("../")
        or target.startswith("/")
        or target.endswith(".ty")
    )


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in [current, *current.parents]:
        if (candidate / PROJECT_FILE).exists():
            return candidate

    raise SyntaxError(
        _diag(
            "E3000",
            1,
            "project.toml not found",
            "Run command from project root (or subdirectory inside project).",
        )
    )


def load_manifest(project_root: Path) -> ProjectManifest:
    project_path = project_root / PROJECT_FILE
    if not project_path.exists():
        raise SyntaxError(
            _diag("E3001", 1, "project.toml missing", "Create project.toml in project root.")
        )

    data = tomllib.loads(project_path.read_text())
    project = data.get("project")
    if not isinstance(project, dict):
        raise SyntaxError(
            _diag("E3002", 1, "[project] section missing", "Add [project] section.")
        )

    name = _required_str(project, "name", "E3003")
    if not _NAME_RE.fullmatch(name):
        raise SyntaxError(
            _diag("E3004", 1, f"invalid project name '{name}'", "Use snake_case identifier style.")
        )
    version = _required_str(project, "version", "E3005")
    entry = _required_str(project, "entry", "E3006")

    packages: dict[str, PackageSpec] = {}
    raw_packages = data.get("packages", {})
    if raw_packages is None:
        raw_packages = {}
    if not isinstance(raw_packages, dict):
        raise SyntaxError(_diag("E3009", 1, "[packages] must be table", "Use [packages.<name>] sections."))

    for name_key, pkg_data in raw_packages.items():
        if not isinstance(name_key, str) or not _NAME_RE.fullmatch(name_key):
            raise SyntaxError(
                _diag("E3010", 1, f"invalid package name '{name_key}'", "Use snake_case identifier names.")
            )
        if not isinstance(pkg_data, dict):
            raise SyntaxError(_diag("E3011", 1, f"package '{name_key}' must be table", "Use [packages.<name>] table."))

        git = _required_str(pkg_data, "git", "E3012")
        if "rev" not in pkg_data:
            raise SyntaxError(
                _diag(
                    "E3013",
                    1,
                    f"package '{name_key}' must define `rev`",
                    "Use `rev` with exact git commit SHA.",
                )
            )
        requested = _required_str(pkg_data, "rev", "E3014")
        packages[name_key] = PackageSpec(name=name_key, git=git, requested=requested)

    python_deps: list[str] = []
    raw_python = data.get("python", {})
    if raw_python is None:
        raw_python = {}
    if not isinstance(raw_python, dict):
        raise SyntaxError(_diag("E3015", 1, "[python] must be table", "Use [python].dependencies list."))
    raw_deps = raw_python.get("dependencies", [])
    if raw_deps is None:
        raw_deps = []
    if not isinstance(raw_deps, list) or any(not isinstance(x, str) for x in raw_deps):
        raise SyntaxError(_diag("E3016", 1, "[python].dependencies must be string list", "Use dependency strings."))
    python_deps.extend(raw_deps)

    return ProjectManifest(
        name=name,
        version=version,
        entry=entry,
        packages=packages,
        python_dependencies=python_deps,
    )


def load_lock(project_root: Path) -> ProjectLock | None:
    lock_path = project_root / LOCK_FILE
    if not lock_path.exists():
        return None
    data = tomllib.loads(lock_path.read_text())

    raw_packages = data.get("packages", {})
    if not isinstance(raw_packages, dict):
        raise SyntaxError(_diag("E3020", 1, "invalid project.lock [packages]", "Regenerate lockfile."))

    packages: dict[str, LockedPackage] = {}
    for name, pkg in raw_packages.items():
        if not isinstance(pkg, dict):
            raise SyntaxError(_diag("E3021", 1, f"invalid lock package '{name}'", "Regenerate lockfile."))
        git = _required_str(pkg, "git", "E3022")
        requested = _required_str(pkg, "requested", "E3023")
        commit = _required_str(pkg, "commit", "E3024")
        resolved_version = _required_str(pkg, "resolved_version", "E3025")
        packages[name] = LockedPackage(
            name=name,
            git=git,
            requested=requested,
            commit=commit,
            resolved_version=resolved_version,
        )

    raw_python = data.get("python", {})
    if raw_python is None:
        raw_python = {}
    if not isinstance(raw_python, dict):
        raise SyntaxError(_diag("E3026", 1, "invalid project.lock [python]", "Regenerate lockfile."))
    deps = raw_python.get("dependencies", [])
    if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
        raise SyntaxError(_diag("E3027", 1, "invalid lock python dependencies", "Regenerate lockfile."))

    return ProjectLock(packages=packages, python_dependencies=deps)


def write_lock(project_root: Path, lock: ProjectLock) -> None:
    lines: list[str] = []
    for name in sorted(lock.packages):
        pkg = lock.packages[name]
        lines.append(f"[packages.{name}]")
        lines.append(f'git = "{_escape(pkg.git)}"')
        lines.append(f'requested = "{_escape(pkg.requested)}"')
        lines.append(f'commit = "{_escape(pkg.commit)}"')
        lines.append(f'resolved_version = "{_escape(pkg.resolved_version)}"')
        lines.append("")

    lines.append("[python]")
    lines.append("dependencies = [")
    for dep in lock.python_dependencies:
        lines.append(f'  "{_escape(dep)}",')
    lines.append("]")
    lines.append("")
    (project_root / LOCK_FILE).write_text("\n".join(lines))


def resolve_lock(manifest: ProjectManifest) -> ProjectLock:
    locked_packages: dict[str, LockedPackage] = {}
    for name, spec in manifest.packages.items():
        commit = _resolve_git_ref(spec.git, spec.requested)
        locked_packages[name] = LockedPackage(
            name=name,
            git=spec.git,
            requested=spec.requested,
            commit=commit,
            resolved_version=spec.requested,
        )

    return ProjectLock(
        packages=locked_packages,
        python_dependencies=list(manifest.python_dependencies),
    )


def ensure_cache_dirs(project_root: Path) -> tuple[Path, Path]:
    cache_root = project_root / CACHE_DIR
    build_root = project_root / BUILD_DIR
    cache_root.mkdir(parents=True, exist_ok=True)
    build_root.mkdir(parents=True, exist_ok=True)
    return cache_root, build_root


def materialize_locked_package(project_root: Path, locked: LockedPackage) -> Path:
    cache_root, _ = ensure_cache_dirs(project_root)
    dep_root = cache_root / "deps" / f"{locked.name}-{locked.commit[:12]}"
    if (dep_root / ".git").exists():
        return dep_root

    dep_root.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "clone", "--quiet", locked.git, str(dep_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SyntaxError(
            _diag(
                "E3030",
                1,
                f"failed to clone package '{locked.name}'",
                completed.stderr.strip() or "check git URL and network access",
            )
        )

    checkout = subprocess.run(
        ["git", "-C", str(dep_root), "checkout", "--quiet", locked.commit],
        capture_output=True,
        text=True,
        check=False,
    )
    if checkout.returncode != 0:
        raise SyntaxError(
            _diag(
                "E3031",
                1,
                f"failed to checkout commit '{locked.commit}' for package '{locked.name}'",
                checkout.stderr.strip() or "lockfile commit may be invalid",
            )
        )
    return dep_root


def write_manifest(project_root: Path, manifest: ProjectManifest) -> None:
    lines: list[str] = []
    lines.append("[project]")
    lines.append(f'name = "{_escape(manifest.name)}"')
    lines.append(f'version = "{_escape(manifest.version)}"')
    lines.append(f'entry = "{_escape(manifest.entry)}"')
    lines.append("")

    for key in sorted(manifest.packages):
        pkg = manifest.packages[key]
        lines.append(f"[packages.{key}]")
        lines.append(f'git = "{_escape(pkg.git)}"')
        lines.append(f'rev = "{_escape(pkg.requested)}"')
        lines.append("")

    lines.append("[python]")
    lines.append("dependencies = [")
    for dep in manifest.python_dependencies:
        lines.append(f'  "{_escape(dep)}",')
    lines.append("]")
    lines.append("")

    (project_root / PROJECT_FILE).write_text("\n".join(lines))


def infer_package_name(git_url: str) -> str:
    stem = git_url.rstrip("/").rsplit("/", 1)[-1]
    if stem.endswith(".git"):
        stem = stem[:-4]
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    if not name:
        name = "pkg"
    if not name[0].isalpha() and name[0] != "_":
        name = f"_{name}"
    return name.lower()


def validate_python_import_name(name: str) -> bool:
    return _PY_IMPORT_RE.fullmatch(name) is not None


def _resolve_git_ref(git_url: str, requested: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", requested):
        return requested
    raise SyntaxError(
        _diag(
            "E3032",
            1,
            f"invalid rev '{requested}'",
            "Use exact 40-char git commit SHA in [packages.<name>].rev.",
        )
    )


def _required_str(mapping: dict[str, object], key: str, code: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SyntaxError(_diag(code, 1, f"missing or invalid '{key}'", f"Set `{key}` to non-empty string."))
    return value


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _diag(code: str, line: int, message: str, hint: str) -> str:
    return f"[{code}] Line {line}: {message}. Hint: {hint}"
