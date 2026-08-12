# MESFlow v65.8.33.1

## Docker test environment hotfix

- Adds `MESFLOW_ENV=test` and a dedicated `MESFLOW_SECRET_KEY` to the `tests` service in `compose.test.yml`.
- Keeps the test runner configuration consistent with `mesflow-test-api`.
- Adds an early guard in `scripts/test/run-all.sh` to refuse production mode and unsafe/missing test secrets.
- Fixes pytest collection failures raised by `mesflow.core.config` before unit tests start.

No database migration.
