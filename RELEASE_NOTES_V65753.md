# MESFlow v65.7.5.3

## Single planned quantity source

- `production_orders.planned_quantity` is now the only production target.
- Removed duplicated `plan_qty` columns from runtime and template operations.
- Dashboard, kiosk, KPI, completion logic, Excel import/export and Template instantiation all read the PO target.
- Migration 0012 recovers missing PO quantities from legacy operation values before dropping duplicate columns.
