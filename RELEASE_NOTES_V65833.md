# MESFlow v65.8.33 — Automated PostgreSQL/Docker Test Suite

- Added isolated `compose.test.yml` using PostgreSQL 17 tmpfs storage.
- Added migration, schema, API, night-shift, overlap and Session Exception Center integration tests.
- Added one-command runner that builds, executes and cleans all test containers.
- Added JUnit XML reports under `test-results/`.
- Added GitHub Actions workflow for automatic execution on push and pull request.
