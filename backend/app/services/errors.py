from __future__ import annotations


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class InvalidStateError(DomainError):
    status_code = 409
    code = "invalid_state"


class ContactNotAllowedError(DomainError):
    status_code = 409
    code = "contact_not_allowed"

    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__(
            "This lead cannot be emailed: " + ", ".join(reasons), details={"reasons": reasons}
        )
        self.reasons = reasons
