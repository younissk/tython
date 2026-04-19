import ast
from pathlib import Path

from .custom_frontend import parse_custom_source
from .lowering import lower as lower_ast
from .semantics import check_semantics


def parse(source: str, mode: str = "exec") -> ast.AST:
    source = _normalize_source(source)
    return ast.parse(source, mode=mode)


def parse_custom(source: str) -> ast.AST:
    source = _normalize_source(source)
    frontend = parse_custom_source(source)
    check_semantics(frontend.tree)
    return frontend.tree


def lower(ir: ast.AST) -> ast.AST:
    return lower_ast(ir)


def parse_file(path: str | Path, mode: str = "exec") -> ast.AST:
    file_path = Path(path)
    return parse(file_path.read_text(), mode=mode)


def _normalize_source(source: str) -> str:
    if source.startswith("\ufeff"):
        return source.removeprefix("\ufeff")
    return source
