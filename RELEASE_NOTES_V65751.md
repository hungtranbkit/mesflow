# MESFlow v65.7.5.1

## Deploy fix

- Shorten Alembic revision `0010_template_part_drawing_po_schedule` to `0010`.
- Prevent `alembic_version.version_num VARCHAR(32)` truncation during upgrade.
- Keep migration chain `0009_working_calendar -> 0010`.
- Synchronize runtime, release metadata, schema version, and Docker image tag to 65.7.5.1.
