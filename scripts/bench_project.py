from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _run_json(cmd: list[str], *, cwd: Path) -> tuple[dict[str, object], float]:
    start = time.perf_counter_ns()
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = (time.perf_counter_ns() - start) / 1e6
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\n\n{completed.stdout}{completed.stderr}".strip()
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"expected JSON output from: {' '.join(cmd)}\n\nstdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object, got {type(payload).__name__}")
    return payload, elapsed_ms


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark cold/warm Tython project build/run using the CLI (JSON output)."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to a Tython project root (contains project.toml). Defaults to cwd.",
    )
    parser.add_argument(
        "--run-target",
        type=str,
        default="",
        help="Optional .ty path under src/ to run (e.g. src/main.ty).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove .tython/build and cached artifacts before benchmarking.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON report to this path (also prints if omitted).",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    if args.clean:
        shutil.rmtree(project_root / ".tython" / "build", ignore_errors=True)
        shutil.rmtree(
            project_root / ".tython" / "cache" / "artifacts", ignore_errors=True
        )

    build_cmd = [sys.executable, "-m", "parser.cli_typer", "build", "--json"]
    cold_report, cold_ms = _run_json(build_cmd, cwd=project_root)
    warm_report, warm_ms = _run_json(build_cmd, cwd=project_root)

    payload: dict[str, object] = {
        "project_root": str(project_root),
        "build": {
            "cold_ms": round(cold_ms, 3),
            "warm_ms": round(warm_ms, 3),
            "cold": cold_report,
            "warm": warm_report,
        },
    }

    if args.run_target:
        run_cmd = [
            sys.executable,
            "-m",
            "parser.cli_typer",
            "run",
            args.run_target,
            "--no-sync",
        ]
        # Run twice; report wall-clock time only (runtime output is ignored).
        start = time.perf_counter_ns()
        subprocess.run(run_cmd, cwd=project_root, capture_output=True, text=True, check=True)
        payload["run"] = {"cold_ms": round((time.perf_counter_ns() - start) / 1e6, 3)}

        start = time.perf_counter_ns()
        subprocess.run(run_cmd, cwd=project_root, capture_output=True, text=True, check=True)
        payload["run"]["warm_ms"] = round((time.perf_counter_ns() - start) / 1e6, 3)

    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

