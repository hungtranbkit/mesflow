# MESFlow v65.8.41.3

## QR API fetch_all hotfix

- Fix HTTP 500 on `GET /api/qr-labels`.
- Import `fetch_all` in `master_data.py`; the endpoint previously raised `NameError`.
- Add static regression test ensuring the route dependency is imported.
