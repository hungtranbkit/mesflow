# MESFlow v65.8.16.1

- Validate normalized Template Part codes on tree save and again before PO instantiation.
- Return structured `DUPLICATE_PART_CODE_IN_TEMPLATE` / `EMPTY_PART_CODE` errors instead of raw PostgreSQL exceptions.
- Add `GET /api/templates/{template_id}/validate` for Admin UI and QA Center.
- Correct duplicate Part codes in `DEMO-E10-LAP-RAP` and `DEMO-E10-FULL` seed sources.
- Keep PO cloning inside one database transaction; validation occurs before the PO insert.
- Hide database exception details from API clients while retaining server-side exception logs.
