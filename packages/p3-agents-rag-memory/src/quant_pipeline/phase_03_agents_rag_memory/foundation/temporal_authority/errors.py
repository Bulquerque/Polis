from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: str
    message: str
    artifact_name: str | None = None
    record_id: str | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "artifact_name": self.artifact_name,
            "record_id": self.record_id,
            "field": self.field,
        }


class S2ContractError(ValueError):
    """Fail-closed P3.S2 contract, temporal, or snapshot error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        issues: list[Issue] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.issues = tuple(issues or ())

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "issues": [issue.to_dict() for issue in self.issues],
        }
