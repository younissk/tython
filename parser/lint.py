from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import parse_custom
from .diagnostics import diagnostic_from_exception, render_diagnostic


@dataclass(frozen=True)
class LintResult:
    path: Path
    diagnostics: list[str]


def lint_file(path: Path) -> list[str]:
    try:
        parse_custom(path.read_text())
        return []
    except SyntaxError as exc:
        diagnostic = diagnostic_from_exception(
            exc,
            file=str(path),
            include_trace=False,
            default_phase="typecheck",
        )
        return [render_diagnostic(diagnostic, mode="rich", verbose=False)]


def lint_paths(paths: list[Path]) -> list[LintResult]:
    results: list[LintResult] = []
    for path in paths:
        results.append(LintResult(path=path, diagnostics=lint_file(path)))
    return results


def discover_lint_targets(project_root: Path, paths: list[Path]) -> list[Path]:
    if not paths:
        src_root = project_root / "src"
        if not src_root.exists():
            raise SyntaxError("src/ directory missing")
        return sorted(src_root.rglob("*.ty"))

    targets: list[Path] = []
    for raw in paths:
        path = raw if raw.is_absolute() else (project_root / raw).resolve()
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.ty")))
            continue
        if path.suffix == ".ty":
            targets.append(path)
    return targets


def lint_project(project_root: Path, paths: list[Path]) -> list[LintResult]:
    targets = discover_lint_targets(project_root, paths)
    return lint_paths(targets)
