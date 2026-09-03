"""Common P7 error hierarchy with stable reason codes."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class P7ErrorContext:
    module_id: str | None = None
    artifact_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    field: str | None = None
    details: Mapping[str, Any] | None = None


class P7Error(RuntimeError):
    """Root exception for every fatal P7 failure."""

    def __init__(self, reason_code: str, message: str, context: P7ErrorContext | None = None) -> None:
        self.reason_code = reason_code
        self.message = message
        self.context = context or P7ErrorContext()
        super().__init__(f"{reason_code}: {message}")

    def to_issue(self) -> dict[str, Any]:
        return {
            "code": self.reason_code,
            "message": self.message,
            "module_id": self.context.module_id,
            "artifact_ids": list(self.context.artifact_ids),
            "candidate_ids": list(self.context.candidate_ids),
            "field": self.context.field,
            "details": dict(self.context.details or {}),
            "severity": "FATAL",
        }


class P7ContractError(P7Error):
    """Public or internal contract violation."""


class P7IntegrationError(P7Error):
    """Cross-subphase composition failure."""
