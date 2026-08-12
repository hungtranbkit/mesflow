# MESFlow v65.8.39

## Automated backup restore verification

- Adds a PostgreSQL integration test that creates a real custom-format `pg_dump` backup.
- Restores the backup into a uniquely named isolated database without replacing the source test database.
- Verifies SHA-256 generation, backup manifest, a real MESFlow data marker, Alembic head, required tables, foreign keys, input-consumption ledger, and Error Trace schema.
- Always terminates restore connections and drops the temporary restore database, including on failure.
- The restore test is part of the standard PostgreSQL Docker/JUnit suite.
