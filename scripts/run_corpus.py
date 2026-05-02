from __future__ import annotations

import argparse
import ast
import json
import time
from dataclasses import dataclass
from pathlib import Path

from parser import lower, parse_custom
from parser.custom_frontend.api import parse_custom_source_profiled
from parser.semantics import check_semantics


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CorpusCase:
    source_path: Path
    expected_python: Path | None
    should_pass: bool


def _discover_cases(root: Path, *, split: str) -> list[CorpusCase]:
    cases: list[CorpusCase] = []
    case_root = root / split
    if not case_root.exists():
        return cases

    for source_path in sorted(case_root.rglob("*.ty")):
        expected_python = source_path.with_suffix(".py")
        cases.append(
            CorpusCase(
                source_path=source_path,
                expected_python=expected_python if expected_python.exists() else None,
                should_pass=split != "invalid",
            )
        )
    return cases


def discover_validation_cases(root: Path) -> list[CorpusCase]:
    return [
        *_discover_cases(root, split="valid"),
        *_discover_cases(root, split="invalid"),
    ]


def discover_perf_cases(root: Path) -> list[CorpusCase]:
    return _discover_cases(root, split="perf")


def _validate_case(case: CorpusCase) -> None:
    source = case.source_path.read_text()
    if not case.should_pass:
        try:
            parse_custom(source)
        except SyntaxError:
            return
        raise AssertionError(f"expected {case.source_path} to fail")

    tree = parse_custom(source)
    if case.expected_python is None:
        return

    lowered = lower(tree)
    expected = ast.parse(case.expected_python.read_text(), mode="exec")
    if ast.dump(lowered, include_attributes=False) != ast.dump(
        expected, include_attributes=False
    ):
        raise AssertionError(f"lowered output mismatch for {case.source_path}")
    compile(lowered, str(case.source_path), "exec")


def run_validation(root: Path) -> list[CorpusCase]:
    cases = discover_validation_cases(root)
    for case in cases:
        _validate_case(case)
    return cases


def run_benchmark(root: Path, *, repeat: int = 5, phases: bool = False) -> dict[str, object]:
    cases = discover_perf_cases(root)
    timings: list[dict[str, object]] = []
    start_total = time.perf_counter()
    for case in cases:
        source = case.source_path.read_text()
        expected = (
            ast.parse(case.expected_python.read_text(), mode="exec")
            if case.expected_python is not None
            else None
        )
        start = time.perf_counter()

        phase_totals_ms: dict[str, float] = {}
        for _ in range(repeat):
            if not phases:
                tree = parse_custom(source)
                if expected is not None:
                    lowered = lower(tree)
                    if ast.dump(lowered, include_attributes=False) != ast.dump(
                        expected, include_attributes=False
                    ):
                        raise AssertionError(
                            f"lowered output mismatch for {case.source_path}"
                        )
                    compile(lowered, str(case.source_path), "exec")
                continue

            frontend, rewrite_timings = parse_custom_source_profiled(source)
            for key, value in rewrite_timings.items():
                phase_totals_ms[key] = phase_totals_ms.get(key, 0.0) + float(value)

            t0 = time.perf_counter_ns()
            check_semantics(frontend.tree)
            phase_totals_ms["semantics_ms"] = phase_totals_ms.get("semantics_ms", 0.0) + (
                time.perf_counter_ns() - t0
            ) / 1e6

            t0 = time.perf_counter_ns()
            lowered = lower(frontend.tree)
            phase_totals_ms["lower_ms"] = phase_totals_ms.get("lower_ms", 0.0) + (
                time.perf_counter_ns() - t0
            ) / 1e6

            if expected is not None:
                if ast.dump(lowered, include_attributes=False) != ast.dump(
                    expected, include_attributes=False
                ):
                    raise AssertionError(
                        f"lowered output mismatch for {case.source_path}"
                    )

            t0 = time.perf_counter_ns()
            ast.unparse(lowered)
            phase_totals_ms["unparse_ms"] = phase_totals_ms.get("unparse_ms", 0.0) + (
                time.perf_counter_ns() - t0
            ) / 1e6

            t0 = time.perf_counter_ns()
            compile(lowered, str(case.source_path), "exec")
            phase_totals_ms["compile_ms"] = phase_totals_ms.get("compile_ms", 0.0) + (
                time.perf_counter_ns() - t0
            ) / 1e6

        elapsed = time.perf_counter() - start
        timings.append(
            {
                "path": str(case.source_path.relative_to(root)),
                "seconds": round(elapsed / repeat, 6),
                **(
                    {
                        "phases_ms": {
                            key: round(value / repeat, 3)
                            for key, value in sorted(phase_totals_ms.items())
                        }
                    }
                    if phases
                    else {}
                ),
            }
        )
    return {
        "root": str(root),
        "repeat": repeat,
        "phases": phases,
        "case_count": len(cases),
        "seconds_total": round(time.perf_counter() - start_total, 6),
        "timings": timings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Tython corpus validation or benchmarks."
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT / "corpus")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "check", help="Run validation over corpus fixtures."
    ).add_argument("--json", action="store_true", help="Emit a JSON summary.")

    bench_command = subparsers.add_parser(
        "bench", help="Run repeatable timing over perf fixtures."
    )
    bench_command.add_argument("--repeat", type=int, default=5)
    bench_command.add_argument(
        "--phases",
        action="store_true",
        help="Include per-phase timing breakdown (rewrite/parse/semantics/lower/unparse/compile).",
    )
    bench_command.add_argument(
        "--output", type=Path, help="Write JSON report to this path."
    )
    bench_command.add_argument(
        "--json", action="store_true", help="Emit a JSON report."
    )

    args = parser.parse_args()

    if args.command == "check":
        cases = run_validation(args.root)
        payload = {
            "root": str(args.root),
            "valid_cases": len([case for case in cases if case.should_pass]),
            "invalid_cases": len([case for case in cases if not case.should_pass]),
            "cases": [str(case.source_path.relative_to(args.root)) for case in cases],
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(
                f"Validated {payload['valid_cases']} valid case(s) and {payload['invalid_cases']} invalid case(s)."
            )
        return

    report = run_benchmark(args.root, repeat=args.repeat, phases=args.phases)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    if args.json or args.output is None:
        print(text)


if __name__ == "__main__":
    main()
