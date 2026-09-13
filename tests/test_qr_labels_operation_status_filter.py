from pathlib import Path

SOURCE = Path("app/mesflow/web/master_data.py").read_text(encoding="utf-8")


def test_qr_labels_imports_the_same_runnable_status_sets_kiosk_uses():
    # Single source of truth: the QR-list endpoint must reuse
    # scheduling.py's RUNNABLE_STATUSES rather than duplicating its own copy
    # of the operation-status vocabulary, so the two can never silently drift.
    assert "from mesflow.db.repositories.scheduling import RUNNABLE_STATUSES" in SOURCE


def test_qr_labels_operation_branch_no_longer_hardcodes_active_true():
    # OPERATION branch must still filter by OPERATION status (not a hardcoded
    # `true AS active`) so a COMPLETED/CANCELLED op -- or a REWORK/non-labelled
    # op the kiosk cannot start -- isn't offered as a printable/scannable QR.
    operation_branch = SOURCE.split("elif kind=='OPERATION':", 1)[1].split("elif kind=='PART':", 1)[0]
    assert "true AS active" not in operation_branch
    assert "RUNNABLE_STATUSES" in operation_branch
    # The filter is gated behind active_only (default true), like EMPLOYEE/PART.
    assert "if active_only:" in operation_branch


def test_qr_labels_operation_branch_does_not_gate_by_po_started_status():
    # Yêu cầu: XEM/IN tem QR TRƯỚC khi Start PO. Danh sách QR KHÔNG được lọc
    # theo trạng thái started/running của PO -- chỉ cần PO/Part/OP tồn tại (và
    # OP chưa COMPLETED/CANCELLED). Regression cho việc bỏ gate po.status.
    operation_branch = SOURCE.split("elif kind=='OPERATION':", 1)[1].split("elif kind=='PART':", 1)[0]
    assert "po.status IN" not in operation_branch, "không được lọc QR theo trạng thái PO"
    assert "RUNNABLE_PO_STATUSES" not in operation_branch
