from __future__ import annotations
from enum import StrEnum

class ObserverErrorCode(StrEnum):
    INPUT_MISSING = "P4_S3_INPUT_MISSING"
    INPUT_INVALID = "P4_S3_INPUT_INVALID"
    REGISTRY_INVALID = "P4_S3_REGISTRY_INVALID"
    SPEC_INVALID = "P4_S3_SPEC_INVALID"
    BUDGET_EXCEEDED = "P4_S3_BUDGET_EXCEEDED"
    OBSERVER_NOT_APPROVED = "P4_S3_OBSERVER_NOT_APPROVED"
    OPERATOR_UNSUPPORTED = "P4_S3_OPERATOR_UNSUPPORTED"
    NUMERIC_DOMAIN_ERROR = "P4_S3_NUMERIC_DOMAIN_ERROR"
    OUTPUT_INVALID = "P4_S3_OUTPUT_INVALID"

class ObserverContractError(ValueError):
    def __init__(self, code: ObserverErrorCode, message: str, *, path: str | None = None):
        self.code = code
        self.path = path
        super().__init__(f"{code}: {message}" + (f" @ {path}" if path else ""))
