# MESFlow v65.8.37

- Removed the duplicate Daily Operation Tracking tab; Dashboard remains the single daily operations view.
- Added PostgreSQL operation input consumption ledger.
- Shared upstream availability is calculated across every downstream operation.
- Finish and supervisor edits lock the source operation and update ledger atomically.
- Added migration 0019 with backfill for existing closed downstream sessions.
