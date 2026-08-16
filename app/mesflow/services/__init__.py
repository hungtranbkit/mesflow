"""V66 application/service layer.

Services translate typed commands into calls against the existing
repository layer (`mesflow.db.repositories.*`), which remains the single
source of truth for MESFlow's business invariants and transaction
boundaries. A service's job is: validate the command shape, call the
repository, translate repository errors into the `mesflow.domain.errors`
vocabulary where useful, publish a domain event on success, and return a
typed result -- never raw dicts, never HTTP status codes.
"""
