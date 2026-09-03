"""Structured errors for P7.S7."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..errors import P7Error as CoreP7Error, P7ErrorContext


@dataclass(frozen=True, slots=True)
class ErrorContext:
    module_id: str
    artifact_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    field: str | None = None
    details: Mapping[str, object] | None = None


class P7Error(CoreP7Error):
    """Base structured error."""

    def __init__(self, code: str, message: str, context: ErrorContext) -> None:
        super().__init__(
            code, message,
            P7ErrorContext(
                module_id=context.module_id, artifact_ids=context.artifact_ids,
                candidate_ids=context.candidate_ids, field=context.field, details=context.details,
            ),
        )
        self.code = code
        self.context = context


class ContractViolation(P7Error):
    """Wire contract or schema violation."""


class IntegrityViolation(P7Error):
    """Hash, identity or manifest integrity violation."""


class TemporalViolation(P7Error):
    """Point-in-time violation."""


class PolicyViolation(P7Error):
    """Invalid or unsupported policy."""


class InternalInvariantViolation(P7Error):
    """Internal algorithmic invariant violation."""
