from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from quant_pipeline.phase_09.contracts.base import (
    BacktestId,
    CycleId,
    NonEmptyStr,
    RunId,
    SemanticVersion,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)


class CompatibilityState(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    COMPATIBLE_LIMITED = "COMPATIBLE_LIMITED"
    COMPATIBLE_PROCESS_ISOLATED = "COMPATIBLE_PROCESS_ISOLATED"
    COMPATIBLE_GOVERNED = "COMPATIBLE_GOVERNED"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPATIBLE = "INCOMPATIBLE"


class CompatibilityReceipt(StrictModel):
    phase_id: NonEmptyStr
    package_name: NonEmptyStr
    package_version: NonEmptyStr
    contract_name: NonEmptyStr
    contract_version: NonEmptyStr
    state: CompatibilityState
    checked_at: UtcDateTime
    run_id: RunId | None = None
    cycle_id: CycleId | None = None
    backtest_id: BacktestId | None = None
    source_payload_sha256: Sha256Hex | None = None
    output_payload_sha256: Sha256Hex | None = None
    limitations: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_state(self) -> "CompatibilityReceipt":
        if self.state in {CompatibilityState.INCOMPATIBLE, CompatibilityState.UNAVAILABLE}:
            if not self.reason_codes:
                raise ValueError("unavailable/incompatible receipt requires reason codes")
        if self.state is CompatibilityState.COMPATIBLE and self.limitations:
            raise ValueError("fully compatible receipt cannot carry limitations")
        return self


class SupplementalArtifact(StrictModel):
    role: NonEmptyStr
    payload: object
    schema_name: NonEmptyStr
    schema_document: dict[str, object]
    schema_version: SemanticVersion = "1.0.0"
    producer_module_id: NonEmptyStr
    record_count: int = Field(default=1, ge=0)
    grain: tuple[NonEmptyStr, ...] = ()
    event_time: UtcDateTime | None = None
    maturity_at: UtcDateTime | None = None
    settlement_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_supplement(self) -> "SupplementalArtifact":
        structured = isinstance(self.payload, (dict, list, tuple)) or hasattr(self.payload, "model_dump")
        if not structured:
            raise ValueError("supplemental payload must be a structured object or array")
        if self.schema_document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError("supplemental schema must declare Draft 2020-12")
        if self.schema_document.get("title") != self.schema_name:
            raise ValueError("supplemental schema title must match schema_name")
        if self.schema_document.get("type") not in {"object", "array"}:
            raise ValueError("supplemental schema top-level type must be object or array")
        return self


class P8NativePublicationRequest(StrictModel):
    backtest_id: BacktestId
    producer_package_version: NonEmptyStr
    published_at: UtcDateTime
    require_full: bool = False


class PhaseLineageFingerprint(StrictModel):
    phase_id: NonEmptyStr
    package_name: NonEmptyStr
    package_version: NonEmptyStr
    module_registry_sha256: Sha256Hex | None = None
    schema_registry_sha256: Sha256Hex | None = None
    contract_pack_sha256: Sha256Hex | None = None
    checked_at: UtcDateTime


class LegacyFeedbackHeader(StrictModel):
    feedback_id: NonEmptyStr
    experiment_id: NonEmptyStr
    backtest_id: BacktestId
    created_at: UtcDateTime
    target_phase: NonEmptyStr
    recommended_action: NonEmptyStr
    severity: NonEmptyStr
    valid_for_next_cycle_only: bool = True

    @model_validator(mode="after")
    def next_cycle_only(self) -> "LegacyFeedbackHeader":
        if not self.valid_for_next_cycle_only:
            raise ValueError("legacy feedback is next-cycle-only")
        return self
