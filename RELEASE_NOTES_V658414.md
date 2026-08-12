# MESFlow 65.8.41.4

- Fix HTTP 500 at `GET /api/system/action-logs`.
- Escape literal percent signs in parameterized psycopg SQL noise filters.
- Add regression contract test for the Action Log list query.
