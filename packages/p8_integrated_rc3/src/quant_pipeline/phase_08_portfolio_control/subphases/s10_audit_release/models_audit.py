from __future__ import annotations
from decimal import Decimal
from typing import Literal
from pydantic import Field
from .enums import AuditCheckStatus, AuditOverallStatus, ReasonCode
from .models_common import AuditContext, StrictModel

class AuditCheck(StrictModel):
    check_id: str = Field(min_length=1)
    status: AuditCheckStatus
    reason_codes: tuple[ReasonCode, ...] = ()
    expected_value: str | None = None
    observed_value: str | None = None
    residual: Decimal | None = None
    evidence_ids: tuple[str, ...] = ()

class IndependentAuditReport(StrictModel):
    audit_id: str = Field(min_length=1)
    context: AuditContext
    overall_status: AuditOverallStatus
    checks: tuple[AuditCheck, ...]
    failure_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    replayed_state_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    independent_implementation: bool
    production_promotion_allowed: Literal[False] = False
