from scripts.run_corpus import (
    REPO_ROOT,
    discover_perf_cases,
    run_benchmark,
    run_validation,
)


def test_corpus_validation_runner_handles_valid_and_invalid_fixtures() -> None:
    cases = run_validation(REPO_ROOT / "corpus")

    assert cases
    assert any(case.should_pass for case in cases)
    assert any(not case.should_pass for case in cases)


def test_corpus_perf_runner_reports_timings() -> None:
    report = run_benchmark(REPO_ROOT / "corpus", repeat=1)

    assert report["case_count"] == len(discover_perf_cases(REPO_ROOT / "corpus"))
    assert report["timings"]
