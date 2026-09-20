from pathlib import Path

CSS = Path('app/mesflow/web/static/ui.css').read_text()


def _mobile_block():
    marker = '@media(max-width:620px){.overview-summary:has(.overview-compact-po)'
    start = CSS.index(marker)
    end = CSS.index('\n', start)
    return CSS[start:end]


def test_mobile_overview_uses_two_explicit_semantic_columns():
    block = _mobile_block()
    assert '--overview-compact-columns:minmax(0,1fr) minmax(118px,.46fr)' in block
    assert '.overview-summary .overview-compact-grid{grid-template-columns:var(--overview-compact-columns)' in block
    assert 'grid-column:3' not in block


def test_mobile_overview_values_match_header_rows_and_left_align():
    block = _mobile_block()
    expected = {
        '.compact-plan{grid-column:2;grid-row:1}',
        '.compact-progress{grid-column:1;grid-row:2}',
        '.compact-warning{grid-column:2;grid-row:2}',
        '.compact-repair{grid-column:1;grid-row:3}',
        '.compact-due{grid-column:2;grid-row:3}',
    }
    for rule in expected:
        assert rule in block
    assert '.overview-summary .overview-compact-head{display:grid}' in block
    assert 'justify-self:start;text-align:left' in block


def test_tablet_header_hide_rule_beats_shared_grid_specificity():
    assert '@media(max-width:1099px)' in CSS
    assert '.overview-summary .overview-compact-head{display:none}' in CSS
