from pathlib import Path


def test_qr_labels_fetch_all_is_imported():
    source = Path("app/mesflow/web/master_data.py").read_text(encoding="utf-8")
    assert "from mesflow.db.connection import transaction, fetch_all" in source
    assert "fetch_all(sql,tuple(params))" in source
