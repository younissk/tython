from __future__ import annotations

import ast
from pathlib import Path

from .checker import SemanticChecker
from .constants import BUILTIN_NAMES
from .models import ClassDecl, FunctionSignature, RecordDecl, SemanticAnalysis, Symbol


def check_semantics(
    tree: ast.AST,
    *,
    project_root: Path | None = None,
    source_path: Path | None = None,
) -> None:
    SemanticChecker(project_root=project_root, source_path=source_path).check(tree)


def analyze_semantics(
    tree: ast.AST, *, project_root: Path | None = None, source_path: Path | None = None
) -> SemanticAnalysis:
    checker = SemanticChecker(project_root=project_root, source_path=source_path)
    checker.check(tree)
    return checker.analysis


class PreludeState(dict[str, tuple[str, str | None, bool]]):
    def __init__(
        self,
        symbols: dict[str, tuple[str, str | None, bool]] | None = None,
        *,
        function_signatures: dict[str, FunctionSignature] | None = None,
        record_decls: dict[str, RecordDecl] | None = None,
        class_decls: dict[str, ClassDecl] | None = None,
    ) -> None:
        super().__init__(symbols or {})
        self.function_signatures = function_signatures or {}
        self.record_decls = record_decls or {}
        self.class_decls = class_decls or {}

    @classmethod
    def coerce(
        cls, predeclared: dict[str, tuple[str, str | None, bool]] | PreludeState
    ) -> PreludeState:
        if isinstance(predeclared, cls):
            return cls(
                predeclared,
                function_signatures=dict(predeclared.function_signatures),
                record_decls=dict(predeclared.record_decls),
                class_decls=dict(predeclared.class_decls),
            )
        return cls(predeclared)


# name -> (kind, type_name, initialized)
def check_semantics_with_prelude(
    tree: ast.AST,
    predeclared: dict[str, tuple[str, str | None, bool]] | PreludeState,
    *,
    project_root: Path | None = None,
    source_path: Path | None = None,
) -> PreludeState:
    checker = SemanticChecker(project_root=project_root, source_path=source_path)
    state = PreludeState.coerce(predeclared)
    module_scope = checker._scopes[0]
    for name, (kind, type_name, initialized) in state.items():
        module_scope.symbols[name] = Symbol(
            name=name,
            qualified_name=name,
            kind=kind,
            type_name=type_name,
            py_module=None,
            lineno=0,
            col_offset=0,
            function_id=None,
            initialized=initialized,
        )
    checker._function_signatures = dict(state.function_signatures)
    checker._record_decls = dict(state.record_decls)
    checker._class_decls = dict(state.class_decls)
    checker.check(tree)

    next_symbols = {
        name: (symbol.kind, symbol.type_name, symbol.initialized)
        for name, symbol in checker._scopes[0].symbols.items()
        if name not in BUILTIN_NAMES
    }
    return PreludeState(
        next_symbols,
        function_signatures=dict(checker._function_signatures),
        record_decls=dict(checker._record_decls),
        class_decls=dict(checker._class_decls),
    )
