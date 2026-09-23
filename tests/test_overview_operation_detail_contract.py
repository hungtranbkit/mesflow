from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/mesflow/web/static/pages/overview.js").read_text()
CSS = (ROOT / "app/mesflow/web/static/ui.css").read_text()

def test_overview_operation_rows_are_focusable_and_open_detail():
    assert 'data-op-detail="${x.operation_id}"' in JS
    assert 'tabindex="0"' in JS
    assert "row.ondblclick" in JS
    assert "e.key==='Enter'||e.key===' '" in JS
    assert "showOperationDetail(Number(row.dataset.opDetail))" in JS

def test_operation_detail_uses_existing_report_apis_and_productivity_formula():
    assert "/api/reports/operations/${operationId}" in JS
    assert "/api/reports/operation-sessions?operation_id=${operationId}&limit=3000" in JS
    assert "standard*qty/actual*100" in JS
    assert "Nhanh hơn định mức" in JS
    assert "Chậm hơn định mức" in JS
    assert "định mức × (Đạt + Lỗi) ÷ thời gian thực tế × 100%" in JS

def test_overview_operation_focus_and_modal_styles_exist():
    assert ".overview-op-row[data-op-detail]:hover" in CSS
    assert ".overview-op-row[data-op-detail]:focus-visible" in CSS
    assert ".op-detail-modal" in CSS
    assert ".op-detail-user-row" in CSS

def test_existing_refresh_hotfix_is_preserved():
    assert "userViewing===false" in JS
    assert "},60000);" in JS
