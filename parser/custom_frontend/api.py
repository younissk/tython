from __future__ import annotations

import ast
from dataclasses import dataclass

from .rewriters_brace import rewrite_brace_and_functions
from .rewriters_misc import (
    rewrite_record_literal_blocks,
    rewrite_tokens_combined,
)
from .rewriters_postbrace import rewrite_postbrace_combined


@dataclass(frozen=True)
class CustomFrontendOutput:
    source: str
    tree: ast.AST


def parse_custom_source(source: str) -> CustomFrontendOutput:
    rewritten = rewrite_record_literal_blocks(source)
    rewritten = rewrite_brace_and_functions(rewritten)
    rewritten = rewrite_postbrace_combined(rewritten)
    rewritten = rewrite_tokens_combined(rewritten)
    tree = ast.parse(rewritten, mode="exec")
    return CustomFrontendOutput(source=rewritten, tree=tree)


def parse_custom_source_profiled(source: str) -> tuple[CustomFrontendOutput, dict[str, float]]:
    """Profiled variant for benchmarks: returns output plus timing breakdown (ms)."""
    import time

    timings: dict[str, float] = {}

    t0 = time.perf_counter_ns()
    rewritten = rewrite_record_literal_blocks(source)
    timings["rewrite_pre_brace_ms"] = (time.perf_counter_ns() - t0) / 1e6

    t0 = time.perf_counter_ns()
    rewritten = rewrite_brace_and_functions(rewritten)
    timings["rewrite_brace_ms"] = (time.perf_counter_ns() - t0) / 1e6

    t0 = time.perf_counter_ns()
    rewritten = rewrite_postbrace_combined(rewritten)
    timings["rewrite_post_brace_ms"] = (time.perf_counter_ns() - t0) / 1e6

    t0 = time.perf_counter_ns()
    rewritten = rewrite_tokens_combined(rewritten)
    timings["rewrite_tokens_ms"] = (time.perf_counter_ns() - t0) / 1e6

    t0 = time.perf_counter_ns()
    tree = ast.parse(rewritten, mode="exec")
    timings["ast_parse_ms"] = (time.perf_counter_ns() - t0) / 1e6

    return CustomFrontendOutput(source=rewritten, tree=tree), timings
