# MESFlow 65.8.41.2

- Fix HTTP 500 from `GET /api/qr-labels?type=EMPLOYEE`.
- QR employee catalogue now depends only on stable core employee columns.
- Optional profile columns can no longer make the QR screen blank on upgraded databases.
- Added regression coverage for the employee QR SQL contract.
