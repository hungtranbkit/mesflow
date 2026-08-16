"""V66 domain error vocabulary.

Design choice: MESFlow's repository layer (`mesflow.db.repositories.base`)
already defines `RepositoryError` / `NotFoundError` / `ConflictError`, and
`mesflow.web.errors.api_error_response` already translates them to stable
HTTP status codes used by existing clients (404 / 409 / 400). Rather than
introduce a second, competing hierarchy, this module:

  1. Re-exports the existing repository errors under the same names so
     service code can `raise NotFoundError(...)` / `raise ConflictError(...)`
     without importing the persistence module directly (services should not
     need to know errors live in `db.repositories`).
  2. Adds a small number of genuinely new domain error types the existing
     hierarchy has no equivalent for (`ValidationError`, `InvalidStateError`,
     `PermissionDeniedError`, `InfrastructureError`).

Every domain error carries a `code` class attribute so callers/logs can key
off a stable string instead of the Python class name.
"""
from __future__ import annotations

from mesflow.db.repositories.base import (
    ConflictError as _RepositoryConflictError,
    NotFoundError as _RepositoryNotFoundError,
    RepositoryError as _RepositoryError,
)


class DomainError(Exception):
    """Base type for all service/domain-layer failures.

    Not meant to be raised directly -- raise one of the subclasses below (or
    an existing repository error) so `mesflow.web.errors.api_error_response`
    can map it to a predictable HTTP status.
    """

    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str = ""):
        super().__init__(message or self.code)


class ValidationError(DomainError):
    """Request/command failed structural validation (HTTP 400)."""

    code = "VALIDATION_ERROR"


class PermissionDeniedError(DomainError):
    """Authenticated actor is not allowed to perform this action (HTTP 403)."""

    code = "PERMISSION_DENIED"


class InfrastructureError(DomainError):
    """Underlying infrastructure (DB, external service) failed (HTTP 500)."""

    code = "INFRASTRUCTURE_ERROR"


# Re-exported so `from mesflow.domain.errors import NotFoundError, ConflictError`
# works uniformly for service code, while `mesflow.web.errors` keeps mapping
# the *same* exception classes it always has -- zero behavior change for
# existing routes that still import from `db.repositories.base` directly.
class NotFoundError(_RepositoryNotFoundError, DomainError):
    """Entity does not exist (HTTP 404)."""

    code = "NOT_FOUND"


class ConflictError(_RepositoryConflictError, DomainError):
    """Request conflicts with current state, e.g. a uniqueness violation (HTTP 409)."""

    code = "CONFLICT"


class InvalidStateError(ConflictError):
    """A specific, named kind of conflict: the entity is not in a state that
    allows the requested transition (e.g. finishing an already-CLOSED
    session). Still an HTTP 409 like any other ConflictError, but callers
    and logs can distinguish "invalid state transition" from a generic
    uniqueness/lock conflict."""

    code = "INVALID_STATE"


__all__ = [
    "DomainError",
    "ValidationError",
    "PermissionDeniedError",
    "InfrastructureError",
    "NotFoundError",
    "ConflictError",
    "InvalidStateError",
    "RepositoryError",
]

# Kept importable from here too, unchanged, for convenience.
RepositoryError = _RepositoryError
