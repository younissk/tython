from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceRange:
    start: tuple[int, int]
    end: tuple[int, int]


@dataclass(frozen=True)
class BindingDecl:
    kind: str
    name: str
    type_annotation: str | None
    initializer: ast.expr | None
    has_initializer: bool
    is_public: bool
    location: tuple[int, int]


@dataclass(frozen=True)
class Assignment:
    target: str
    value: ast.expr
    location: tuple[int, int]


@dataclass(frozen=True)
class FunctionParam:
    name: str
    type_name: str
    has_default: bool
    location: tuple[int, int]


@dataclass(frozen=True)
class FunctionSignature:
    name: str
    params: list[FunctionParam]
    return_type: str
    throws: list[str] = field(default_factory=list)
    is_public: bool = False
    location: tuple[int, int] = (1, 1)


@dataclass(frozen=True)
class RecordFieldDecl:
    name: str
    type_name: str
    location: tuple[int, int]


@dataclass(frozen=True)
class RecordDecl:
    name: str
    fields: list[RecordFieldDecl]
    is_public: bool
    location: tuple[int, int]


@dataclass(frozen=True)
class ClassMemberDecl:
    kind: str
    name: str
    type_name: str | None
    initializer: ast.expr | None
    has_initializer: bool
    is_public: bool
    location: tuple[int, int]


@dataclass(frozen=True)
class ClassDecl:
    name: str
    conforms_to: str | None
    is_public: bool
    members: list[ClassMemberDecl]
    methods: dict[str, FunctionSignature]
    setup_count: int
    location: tuple[int, int]


@dataclass
class Symbol:
    name: str
    qualified_name: str
    kind: str
    type_name: str | None
    py_module: str | None
    lineno: int
    col_offset: int
    function_id: int | None
    initialized: bool
    matrix_rank: int | None = None
    matrix_element_type: str | None = None
    parent: str | None = None
    is_public: bool = False


@dataclass(frozen=True)
class ReferenceSite:
    name: str
    qualified_name: str
    location: SourceRange
    kind: str


@dataclass(frozen=True)
class SemanticSymbol:
    name: str
    qualified_name: str
    kind: str
    detail: str | None
    type_name: str | None
    location: SourceRange
    selection_range: SourceRange
    children: list["SemanticSymbol"] = field(default_factory=list)
    is_public: bool = False
    container_name: str | None = None


@dataclass
class TypeContext:
    """Type information needed by the lowering / optimization passes.

    This bundles the post-check-time view of the program that downstream
    consumers (the lowerer, future optimization passes) need to make
    type-driven decisions: emitting __slots__, devirtualizing method calls,
    selecting specialized numeric ops, deciding numba/mypyc eligibility, etc.

    Treat as read-only after SemanticChecker.check() returns.
    """

    class_decls: dict[str, "ClassDecl"] = field(default_factory=dict)
    record_decls: dict[str, "RecordDecl"] = field(default_factory=dict)
    function_signatures: dict[str, "FunctionSignature"] = field(default_factory=dict)
    module_symbols: dict[str, "Symbol"] = field(default_factory=dict)


@dataclass
class SemanticAnalysis:
    symbols_by_name: dict[str, SemanticSymbol] = field(default_factory=dict)
    symbols_by_qualified_name: dict[str, SemanticSymbol] = field(default_factory=dict)
    references_by_name: dict[str, list[ReferenceSite]] = field(default_factory=dict)
    references_by_qualified_name: dict[str, list[ReferenceSite]] = field(
        default_factory=dict
    )
    top_level_symbols: list[SemanticSymbol] = field(default_factory=list)
    diagnostics: list[object] = field(default_factory=list)
    type_context: TypeContext = field(default_factory=lambda: TypeContext())


@dataclass
class Scope:
    kind: str
    function_id: int | None
    symbols: dict[str, Symbol]
