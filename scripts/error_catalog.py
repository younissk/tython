from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

from parser.diagnostics import DIAGNOSTIC_SCHEMA_VERSION


REPO_ROOT = Path(__file__).resolve().parents[1]
DIRECT_CODE_RE = re.compile(r"\[(?P<code>[ERP]\d{4})\]")


@dataclass(frozen=True)
class ErrorCatalogEntry:
    code: str
    area: str
    source: str
    summary: str


def _source_files(root: Path) -> list[Path]:
    files = sorted((root / "parser").rglob("*.py"))
    main_py = root / "main.py"
    if main_py.exists():
        files.append(main_py)
    return files


def _area_for_path(path: Path) -> str:
    parts = path.parts
    if "custom_frontend" in parts:
        return "parse"
    if "semantics" in parts:
        return "typecheck"
    if path.name == "project.py":
        return "project"
    if path.name == "project_build.py":
        return "build"
    if path.name == "diagnostics.py":
        return "diagnostics"
    if path.name == "lint.py":
        return "lint"
    return "runtime"


def _summarize(line: str) -> str:
    text = " ".join(line.strip().split())
    if len(text) <= 96:
        return text
    return text[:93].rstrip() + "..."


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _node_summary(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node) or ""
    if not segment:
        segment = ast.unparse(node) if hasattr(ast, "unparse") else ""
    return _summarize(segment)


def _codes_from_call(node: ast.Call, source: str) -> list[str]:
    name = _call_name(node.func)
    if name in {"err", "_diag"} and node.args:
        code = _constant_string(node.args[0])
        return [code] if code else []
    if name == "make_diagnostic":
        for keyword in node.keywords:
            if keyword.arg == "code":
                code = _constant_string(keyword.value)
                return [code] if code else []
    if name == "SyntaxError" and node.args:
        segment = ast.get_source_segment(source, node.args[0])
        if segment is not None:
            return DIRECT_CODE_RE.findall(segment)
    return []


def _codes_from_assign(node: ast.Assign) -> list[str]:
    codes: list[str] = []
    if not any(
        isinstance(target, ast.Name) and target.id == "code" for target in node.targets
    ):
        return codes

    value = node.value
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        if DIRECT_CODE_RE.fullmatch(f"[{value.value}]"):
            codes.append(value.value)
        return codes

    if isinstance(value, ast.IfExp):
        for branch in (value.body, value.orelse):
            if isinstance(branch, ast.Constant) and isinstance(branch.value, str):
                if re.fullmatch(r"[ERP]\d{4}", branch.value):
                    codes.append(branch.value)
    return codes


def collect_error_catalog(root: Path = REPO_ROOT) -> list[ErrorCatalogEntry]:
    entries: dict[str, ErrorCatalogEntry] = {}
    for path in _source_files(root):
        rel = path.relative_to(root)
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                codes = _codes_from_call(node, source)
            elif isinstance(node, ast.Assign):
                codes = _codes_from_assign(node)
            else:
                continue
            for code in codes:
                if code in entries:
                    continue
                summary = _node_summary(source, node)
                entries[code] = ErrorCatalogEntry(
                    code=code,
                    area=_area_for_path(rel),
                    source=f"{rel}:{getattr(node, 'lineno', 1)}",
                    summary=summary,
                )
    return sorted(
        entries.values(),
        key=lambda entry: (entry.code[0], entry.code[1:], entry.source),
    )


def render_markdown(entries: list[ErrorCatalogEntry]) -> str:
    lines = [
        "# Error Code Catalog",
        "",
        f"Schema version: `{DIAGNOSTIC_SCHEMA_VERSION}`",
        "",
        "This catalog is generated from the parser source. The source location is the canonical",
        "reference for behavior and wording.",
        "",
    ]

    grouped: dict[str, list[ErrorCatalogEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.code[0], []).append(entry)

    order = ["E", "R", "P"]
    for prefix in order:
        if prefix not in grouped:
            continue
        title = {
            "E": "Validation and project errors",
            "R": "Runtime errors",
            "P": "Panic and internal errors",
        }[prefix]
        lines.extend(
            [
                f"## {title}",
                "",
                "| Code | Area | Source | Summary |",
                "| --- | --- | --- | --- |",
            ]
        )
        for entry in grouped[prefix]:
            summary = entry.summary.replace("|", "\\|")
            lines.append(
                f"| `{entry.code}` | {entry.area} | `{entry.source}` | {summary} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_catalog(path: Path, root: Path = REPO_ROOT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(collect_error_catalog(root)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Tython error code catalog."
    )
    parser.add_argument(
        "--write", type=Path, help="Write markdown to this path instead of stdout."
    )
    args = parser.parse_args()

    if args.write is not None:
        write_catalog(args.write)
        return

    print(render_markdown(collect_error_catalog()))


if __name__ == "__main__":
    main()
