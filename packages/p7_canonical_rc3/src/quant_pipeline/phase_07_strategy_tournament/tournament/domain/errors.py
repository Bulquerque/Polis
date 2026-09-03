from __future__ import annotations

from typing import Any

from ...errors import P7Error, P7ErrorContext


class P7TournamentError(P7Error):
    """Base error for Tournament subphases S3 and S4."""

    def __init__(self, code: str, message: str, *, module_id: str, details: dict[str, Any] | None = None) -> None:
        self.module_id = module_id
        self.details = details or {}
        super().__init__(code, message, P7ErrorContext(module_id=module_id, details=self.details))
        self.code = code

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "module_id": self.module_id,
            "details": dict(self.details),
        }


# Backward-compatible aliases for subphase-specific callers.
P7S3Error = P7TournamentError
P7S4Error = P7TournamentError


class ContractViolation(P7TournamentError):
    pass


class IntegrityViolation(P7TournamentError):
    pass


class TemporalViolation(P7TournamentError):
    pass


class PolicyViolation(P7TournamentError):
    pass


class ResourceBudgetExceeded(P7TournamentError):
    pass


class InternalInvariantViolation(P7TournamentError):
    pass
