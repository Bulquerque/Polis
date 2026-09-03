"""Structured errors for P7.S2 with stable reason codes."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import JsonValue

from .reason_codes import ReasonCode
from ..errors import P7Error, P7ErrorContext


@dataclass(slots=True)
class P7S2Error(P7Error):
    code: ReasonCode
    message: str
    module_id: str
    details: dict[str, JsonValue] = field(default_factory=dict)
    retryable: bool = False

    def __post_init__(self) -> None:
        P7Error.__init__(self, self.code.value, self.message, P7ErrorContext(module_id=self.module_id, details=self.details))

    def to_issue(self) -> dict[str, JsonValue]:
        return {
            "code": self.code.value,
            "message": self.message,
            "module_id": self.module_id,
            "details": self.details,
            "retryable": self.retryable,
            "severity": "FATAL",
        }
