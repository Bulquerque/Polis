from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from .enums import AdaptationDecision, AdaptationKind, ReasonCode, RuntimeMode
from .models_common import ArtifactRef, RuntimeContext, StrictModel
from .models_control import SafetySupervisorResult
from .models_invariants import InvariantMonitorResult
from .models_shadow import ShadowEvaluationResult
from .models_shift import ShiftMonitorResult


class AdaptationBound(StrictModel):
    kind: AdaptationKind
    minimum_value: Decimal
    maximum_value: Decimal

    @model_validator(mode="after")
    def ordered(self) -> "AdaptationBound":
        if self.minimum_value > self.maximum_value:
            raise ValueError("minimum_value cannot exceed maximum_value")
        return self


class AdaptationRequest(StrictModel):
    adaptation_id: str = Field(min_length=1)
    kind: AdaptationKind
    previous_value: Decimal
    proposed_value: Decimal
    source_policy_id: str = Field(min_length=1)


class AdaptationRecord(StrictModel):
    adaptation_id: str
    kind: AdaptationKind
    previous_value: Decimal
    proposed_value: Decimal
    decision: AdaptationDecision
    reason_codes: tuple[ReasonCode, ...]


class RuntimeEvidenceBundle(StrictModel):
    bundle_id: str = Field(min_length=1)
    context: RuntimeContext
    shift_result: ShiftMonitorResult
    invariant_result: InvariantMonitorResult
    supervisor_result: SafetySupervisorResult
    shadow_result: ShadowEvaluationResult | None
    adaptations: tuple[AdaptationRecord, ...]
    source_artifacts: tuple[ArtifactRef, ...]
    production_promotion_allowed: bool = False


class RuntimeAssuranceRequest(StrictModel):
    context: RuntimeContext
    shift_request: "ShiftMonitorRequest"
    invariant_request: "InvariantMonitorRequest"
    exposure_state: "ExecutionExposureState"
    supervisor_policy: "SupervisorPolicy"
    shadow_request: "ShadowEvaluationRequest | None" = None
    adaptation_requests: tuple[AdaptationRequest, ...] = ()
    adaptation_bounds: tuple[AdaptationBound, ...] = ()
    source_artifacts: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def shared_context(self) -> "RuntimeAssuranceRequest":
        if self.shift_request.context != self.context:
            raise ValueError("shift_request context must equal root context")
        if self.invariant_request.context != self.context:
            raise ValueError("invariant_request context must equal root context")
        if self.shadow_request is not None and self.shadow_request.context != self.context:
            raise ValueError("shadow_request context must equal root context")
        return self


class RuntimeAssuranceResult(StrictModel):
    evidence_bundle: RuntimeEvidenceBundle
    runtime_mode: RuntimeMode
    generated_at: datetime


from .models_control import ExecutionExposureState, SupervisorPolicy
from .models_invariants import InvariantMonitorRequest
from .models_shadow import ShadowEvaluationRequest
from .models_shift import ShiftMonitorRequest

RuntimeAssuranceRequest.model_rebuild()
