from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_exception_query_avoids_reserved_overlaps_cte_name():
    source = (ROOT / 'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')
    block = source[source.index('def session_exceptions('):source.index('def update_session_exception_reviews(')]
    assert 'WITH overlap_flags AS (' in block
    assert 'WITH overlaps AS (' not in block


def test_exception_page_defines_its_element_lookup_locally():
    source = (ROOT / 'app/mesflow/web/static/pages/session-exceptions.js').read_text(encoding='utf-8')
    assert "const el=id=>document.getElementById(id);" in source
