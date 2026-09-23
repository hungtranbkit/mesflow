from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'app/mesflow/web/static/pages/overview.js').read_text()
CSS=(ROOT/'app/mesflow/web/static/ui.css').read_text()

def test_open_session_keeps_action_column_placeholder():
    assert 'op-session-no-action' in JS
    assert 'aria-hidden="true">—</span>' in JS

def test_session_rows_use_named_cells():
    for cls in ('employee','period','quantity','duration','benchmark'):
        assert f'op-session-cell {cls}' in JS

def test_desktop_cells_are_pinned_to_columns():
    for cls,col in [('employee',1),('period',2),('quantity',3),('duration',4),('benchmark',5)]:
        assert f'.op-detail-session-row .op-session-cell.{cls}{{grid-column:{col}}}' in CSS
    assert '.op-detail-session-row .op-session-actions{grid-column:6}' in CSS
