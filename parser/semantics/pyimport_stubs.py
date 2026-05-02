from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .models import FunctionParam, FunctionSignature


_PRIMITIVES: set[str] = {"int", "float", "bool", "str"}


@dataclass(frozen=True)
class StubModule:
    functions: dict[str, FunctionSignature]
    variables: dict[str, str]


class PyImportStubIndex:
    def __init__(self, stubs_root: Path) -> None:
        self._root = stubs_root
        self._cache: dict[str, StubModule] = {}

    def lookup_function(self, module: str, attr: str) -> FunctionSignature | None:
        stub = self._load(module)
        if stub is None:
            return None
        return stub.functions.get(attr)

    def lookup_variable(self, module: str, attr: str) -> str | None:
        stub = self._load(module)
        if stub is None:
            return None
        return stub.variables.get(attr)

    def _load(self, module: str) -> StubModule | None:
        cached = self._cache.get(module)
        if cached is not None:
            return cached

        path = self._root / (module.replace(".", "/") + ".pyi")
        if not path.exists():
            self._cache[module] = StubModule(functions={}, variables={})
            return self._cache[module]

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            # Stubs are optional; invalid stubs should not break type checking.
            self._cache[module] = StubModule(functions={}, variables={})
            return self._cache[module]

        functions: dict[str, FunctionSignature] = {}
        variables: dict[str, str] = {}

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                sig = _function_signature_from_stub(node)
                if sig is not None:
                    functions[node.name] = sig
                continue
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                type_name = _annotation_to_tython_type(node.annotation)
                if type_name is not None:
                    variables[node.target.id] = type_name

        self._cache[module] = StubModule(functions=functions, variables=variables)
        return self._cache[module]


def _function_signature_from_stub(node: ast.FunctionDef) -> FunctionSignature | None:
    return_type = _annotation_to_tython_type(node.returns) if node.returns else None
    if return_type is None:
        # No (usable) return type -> treat as dynamic.
        return None

    params: list[FunctionParam] = []
    all_args = list(node.args.posonlyargs) + list(node.args.args)
    defaults = list(node.args.defaults)
    default_start = len(all_args) - len(defaults)

    for idx, arg in enumerate(all_args):
        if arg.arg == "self":
            continue
        param_type = _annotation_to_tython_type(arg.annotation) if arg.annotation else None
        if param_type is None:
            # Unknown param types are treated as permissive (py:any).
            param_type = "py:any"
        params.append(
            FunctionParam(
                name=arg.arg,
                type_name=param_type,
                has_default=(idx >= default_start),
                location=(getattr(arg, "lineno", 1), getattr(arg, "col_offset", 0) + 1),
            )
        )

    return FunctionSignature(
        name=node.name,
        params=params,
        return_type=return_type,
        throws=[],
        is_public=True,
        location=(getattr(node, "lineno", 1), getattr(node, "col_offset", 0) + 1),
    )


def _annotation_to_tython_type(annotation: ast.expr | None) -> str | None:
    if annotation is None:
        return None

    if isinstance(annotation, ast.Constant):
        if annotation.value is None:
            return "none"
        return None

    if isinstance(annotation, ast.Name):
        if annotation.id == "None":
            return "none"
        if annotation.id in _PRIMITIVES:
            return annotation.id
        if annotation.id in {"Any", "object"}:
            return None
        return None

    if isinstance(annotation, ast.Subscript):
        # list[T] / Sequence[T] / typing.Sequence[T]
        container = annotation.value
        container_name: str | None = None
        if isinstance(container, ast.Name):
            container_name = container.id
        elif isinstance(container, ast.Attribute) and isinstance(container.value, ast.Name):
            if container.value.id == "typing":
                container_name = container.attr
        if container_name not in {"list", "Sequence"}:
            return None

        inner = _annotation_to_tython_type(annotation.slice)
        if inner is None:
            return None
        return f"{inner}[]"

    return None

