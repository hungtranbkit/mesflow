# MESFlow 65.8.3

- Thêm Force Delete Production Order dành cho giai đoạn test.
- Yêu cầu nhập lại chính xác mã PO và xác nhận hai lần.
- Xóa trong một transaction các session, QC, điều chỉnh, penalty, kiosk event và idempotency liên quan trước khi xóa PO.
- Có thể tắt khi production bằng `MESFLOW_ENABLE_FORCE_DELETE_PO=0`.
