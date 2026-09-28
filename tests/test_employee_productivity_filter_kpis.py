from pathlib import Path

def test_filtered_rows_recalculate_kpis_and_average_productivity():
    js = Path("app/mesflow/web/static/pages/employee-productivity.js").read_text()
    assert "const summaryForVisibleRows = visible =>" in js
    assert "avg_employee_productivity_percent: scored.length ? scored.reduce((n, x) => n + x, 0) / scored.length : null" in js
    assert "drawKpis(summaryForVisibleRows(rows));" in js
    assert "lastSummary = d.summary || {};" in js
    assert "drawKpis(d.summary || {});" not in js
