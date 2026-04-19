from __future__ import annotations

import ast
from dataclasses import dataclass


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


@dataclass(frozen=True)
class FunctionSignature:
    name: str
    params: list[FunctionParam]
    return_type: str
    is_public: bool = False


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
    kind: str
    type_name: str | None
    lineno: int
    function_id: int | None
    initialized: bool


@dataclass
class Scope:
    kind: str
    function_id: int | None
    symbols: dict[str, Symbol]
