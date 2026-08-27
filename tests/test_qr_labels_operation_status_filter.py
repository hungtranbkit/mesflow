from pathlib import Path

SOURCE = Path("app/mesflow/web/master_data.py").read_text(encoding="utf-8")


def test_qr_labels_imports_the_same_runnable_status_sets_kiosk_uses():
    # Single source of truth: the QR-list endpoint must reuse
    # scheduling.py's RUNNABLE_STATUSES/RUNNABLE_PO_STATUSES rather than
    # duplicating its own copy of the status vocabulary, so the two can
    # never silently drift apart.
    assert "from mesflow.db.repositories.scheduling import RUNNABLE_STATUSES,RUNNABLE_PO_STATUSES" in SOURCE


def test_qr_labels_operation_branch_no_longer_hardcodes_active_true():
    # Real bug report: the OPERATION branch of GET /api/qr-labels used to
    # return `true AS active` unconditionally and applied no status filter
    # at all, so a COMPLETED/CANCELLED operation, or one whose parent PO
    # hadn't been Started yet, still showed up (and could be printed) in
    # the QR catalogue -- scanning that QR at the kiosk then failed with
    # OPERATION_NOT_WORKABLE, an error the operator had no way to avoid.
    operation_branch = SOURCE.split("elif kind=='OPERATION':", 1)[1].split("elif kind=='PART':", 1)[0]
    assert "true AS active" not in operation_branch
    assert "RUNNABLE_STATUSES" in operation_branch
    assert "RUNNABLE_PO_STATUSES" in operation_branch
    # The filter must be gated behind active_only (default true), matching
    # the EMPLOYEE/PART branches' existing convention -- never an
    # unconditional, un-overridable hard filter.
    assert "if active_only:" in operation_branch
