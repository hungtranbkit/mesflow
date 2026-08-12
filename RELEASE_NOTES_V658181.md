# MESFlow v65.8.18.2

## Deploy and KPI hotfix

- Fixed Alembic 0016 down_revision to reference actual revision `0015`.
- Fixed `/api/kpi/operations` PostgreSQL GROUP BY using `po.id`.
- No additional schema changes beyond migration 0016.
