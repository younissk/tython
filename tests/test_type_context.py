"""Tests for the TypeContext plumbing between SemanticChecker and lower().

These tests do not assert anything about lowering output — they just verify
that the type information flows through the pipeline so that downstream
optimization passes (currently being built on top) have a stable contract
to consume.
"""

from __future__ import annotations

import ast

import pytest

from parser import parse_custom_with_analysis
from parser.core import lower
from parser.lowering import _LowerCustomIR
from parser.semantics import (
    SemanticAnalysis,
    TypeContext,
    analyze_semantics,
    check_semantics,
)
from parser.custom_frontend import parse_custom_source


def _parse(source: str) -> ast.AST:
    return parse_custom_source(source).tree


def test_check_semantics_populates_type_context() -> None:
    """SemanticChecker.check() must leave a populated TypeContext on the
    analysis object."""
    source = """\
record Animal {
    name: str
}

class Fish is Animal {
    init var name: str
    var age: int = 0

    pub func speak() -> none {
        print(this.name)
    }
}

func greet(who: str) -> str {
    return who
}
"""
    tree = _parse(source)
    analysis = analyze_semantics(tree)

    assert isinstance(analysis, SemanticAnalysis)
    assert isinstance(analysis.type_context, TypeContext)

    ctx = analysis.type_context
    assert "Animal" in ctx.record_decls, ctx.record_decls
    assert "Fish" in ctx.class_decls, ctx.class_decls
    assert "greet" in ctx.function_signatures, ctx.function_signatures


def test_type_context_class_carries_field_set() -> None:
    """The class decl in TypeContext must carry the field set the lowerer
    needs to emit __slots__ in a future Tier 2 pass."""
    source = """\
class Point {
    var x: float = 0.0
    var y: float = 0.0
}
"""
    tree = _parse(source)
    analysis = analyze_semantics(tree)

    point = analysis.type_context.class_decls["Point"]
    field_names = {member.name for member in point.members}
    assert {"x", "y"} <= field_names, field_names


def test_lower_accepts_type_context_kwarg() -> None:
    """lower() must accept a type_context kwarg without complaint and
    propagate it into the visitor."""
    tree, analysis = parse_custom_with_analysis(
        """\
class Box {
    var value: int = 0
}
"""
    )

    # Sanity: the public lower() forwards the kwarg.
    lowered = lower(tree, type_context=analysis.type_context)
    assert isinstance(lowered, ast.Module)


def test_lower_visitor_stores_type_context() -> None:
    """The internal visitor must remember the TypeContext so future
    optimization passes can consult it."""
    tree, analysis = parse_custom_with_analysis(
        """\
class Box {
    var value: int = 0
}
"""
    )

    visitor = _LowerCustomIR(
        native_import_map={},
        file_import_map={},
        type_context=analysis.type_context,
    )
    assert visitor._type_context is analysis.type_context
    assert "Box" in visitor._type_context.class_decls


def test_lower_without_type_context_still_works() -> None:
    """Backwards compatibility: lower() must still run with no type_context
    (REPL, ad-hoc tests, etc.) and produce valid Python."""
    tree = _parse(
        """\
func add(a: int, b: int) -> int {
    return a + b
}
"""
    )
    # Existing call-site shape — no analysis, no context. Must not error.
    check_semantics(tree)
    lowered = lower(tree)
    rendered = ast.unparse(lowered)
    # Sanity check: emitted code parses as valid Python.
    ast.parse(rendered)


def test_type_context_default_factory_is_independent() -> None:
    """Two SemanticAnalysis instances must not share the same TypeContext
    instance via a mutable default."""
    a1 = SemanticAnalysis()
    a2 = SemanticAnalysis()
    assert a1.type_context is not a2.type_context
