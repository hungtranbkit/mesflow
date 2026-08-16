"""V66 domain layer: errors, events, audit -- shared by all services.

This package holds cross-cutting domain concepts (error vocabulary, the
in-process event bus, the transactional audit helper) that services and
repositories depend on. It intentionally does not hold per-table business
logic -- that stays in `mesflow.db.repositories.*`, which remains the single
source of truth for MESFlow's existing invariants (see AGENTS.md).
"""
