from scripts.error_catalog import REPO_ROOT, collect_error_catalog, render_markdown


def test_error_catalog_matches_published_document() -> None:
    expected = render_markdown(collect_error_catalog(REPO_ROOT))
    actual = (REPO_ROOT / "docs/reference/error-codes.md").read_text()

    assert actual == expected


def test_error_catalog_contains_unique_codes() -> None:
    catalog = collect_error_catalog(REPO_ROOT)
    codes = [entry.code for entry in catalog]

    assert len(codes) == len(set(codes))
    assert {"E2024", "E3202", "R0001", "P0001"}.issubset(set(codes))
