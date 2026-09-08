from app.parser import parse_pdf
from scripts.benchmark_parser_backends import STRONG_OCR_REASONS, _percentile
from scripts.generate_parser_benchmark_fixtures import generate


def test_parser_benchmark_fixtures_cover_native_layout_and_scan(tmp_path) -> None:
    paths = {path.name: path for path in generate(tmp_path)}

    narrative = parse_pdf(paths["unseen-narrative.pdf"].read_bytes())
    columns = parse_pdf(paths["unseen-multicolumn.pdf"].read_bytes())
    tables = parse_pdf(paths["unseen-table-heavy.pdf"].read_bytes())
    scanned = parse_pdf(paths["unseen-scanned.pdf"].read_bytes())

    assert len(narrative.pages) == 18
    assert len(columns.pages) == 12
    assert len(tables.pages) == 8
    assert len(scanned.pages) == 3
    assert all(page.text.strip() for page in narrative.pages + columns.pages + tables.pages)
    assert all(not page.text.strip() for page in scanned.pages)
    assert STRONG_OCR_REASONS == {"no-text", "garbled", "vector-text", "scanned"}


def test_parser_benchmark_percentile_is_deterministic() -> None:
    assert _percentile([4.0, 1.0, 3.0, 2.0], 0.95) == 4.0
    assert _percentile([], 0.95) is None
