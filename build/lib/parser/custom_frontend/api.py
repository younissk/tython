from __future__ import annotations

import ast
from dataclasses import dataclass

from .rewriters_brace import rewrite_brace_and_functions
from .rewriters_misc import (
    rewrite_lowercase_literals,
    rewrite_named_call_args,
    rewrite_record_literal_blocks,
    rewrite_this_references,
    rewrite_try_propagation,
)
from .rewriters_structured import rewrite_bindings, rewrite_enum_blocks
from .rewriters_ternary import rewrite_ternary_expressions


@dataclass(frozen=True)
class CustomFrontendOutput:
    source: str
    tree: ast.AST


def parse_custom_source(source: str) -> CustomFrontendOutput:
    rewritten = rewrite_record_literal_blocks(source)
    rewritten = rewrite_this_references(rewritten)
    rewritten = rewrite_brace_and_functions(rewritten)
    rewritten = rewrite_enum_blocks(rewritten)
    rewritten = rewrite_bindings(rewritten)
    rewritten = rewrite_ternary_expressions(rewritten)
    rewritten = rewrite_try_propagation(rewritten)
    rewritten = rewrite_named_call_args(rewritten)
    rewritten = rewrite_lowercase_literals(rewritten)
    tree = ast.parse(rewritten, mode="exec")
    return CustomFrontendOutput(source=rewritten, tree=tree)
