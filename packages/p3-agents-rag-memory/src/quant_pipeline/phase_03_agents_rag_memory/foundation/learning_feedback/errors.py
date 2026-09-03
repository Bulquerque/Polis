from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: str
    message: str
    artifact_name: str | None = None
    record_id: str | None = None
    field: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "artifact_name": self.artifact_name,
            "record_id": self.record_id,
            "field": self.field,
        }


class S3ContractError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
