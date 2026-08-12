# MESFlow v65.8.44 – Rework flow

- Adds `rework_qty` as a subset of `defect_qty`; true scrap is derived as `defect_qty - rework_qty`.
- Session finish, supervisor edit and legacy ESP group-finish APIs accept `rework_qty` and enforce `0 <= rework_qty <= defect_qty`.
- Operation totals retain rework quantity; PO/session management screens show rework and derived scrap.
- Material-flow input can consume either `GOOD` output or `REWORK` output from the selected source operation.
- Template/PO Operation editors expose input source kind: **Đạt** / **Lỗi sửa được**.
- Input Consumption Ledger records `source_qty_kind`; normal and rework pools are allocated independently.
- Repair Operations can therefore use only the available rework pool of an upstream Operation.
- Database migration head: `0022_rework_flow`.

Kiosk companion firmware: ESP32 Kiosk v5.1.9 Rework.
