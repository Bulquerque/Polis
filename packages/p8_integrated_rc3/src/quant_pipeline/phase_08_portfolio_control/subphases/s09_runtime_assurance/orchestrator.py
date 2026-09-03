from __future__ import annotations

import hashlib

from .bounded_adaptation import evaluate_adaptations
from .invariant_monitor import run_invariant_monitor
from .models_control import SafetySupervisorRequest
from .models_evidence import (
    RuntimeAssuranceRequest,
    RuntimeAssuranceResult,
    RuntimeEvidenceBundle,
)
from .safety_supervisor import run_safety_supervisor
from .shadow_evaluator import run_shadow_evaluation
from .shift_monitor import run_shift_monitor


def _bundle_id(request: RuntimeAssuranceRequest) -> str:
    raw = f"{request.context.run_id}|{request.context.cycle_id}|{request.context.observed_at.isoformat()}"
    return "reb_" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def run_runtime_assurance(request: RuntimeAssuranceRequest) -> RuntimeAssuranceResult:
    shift_result = run_shift_monitor(request.shift_request)
    invariant_result = run_invariant_monitor(request.invariant_request)
    supervisor_request = SafetySupervisorRequest(
        context=request.context,
        shift_result=shift_result,
        invariant_result=invariant_result,
        exposure_state=request.exposure_state,
        policy=request.supervisor_policy,
    )
    supervisor_result = run_safety_supervisor(supervisor_request)
    shadow_result = None if request.shadow_request is None else run_shadow_evaluation(request.shadow_request)
    adaptations = evaluate_adaptations(request.adaptation_requests, request.adaptation_bounds)
    bundle = RuntimeEvidenceBundle(
        bundle_id=_bundle_id(request),
        context=request.context,
        shift_result=shift_result,
        invariant_result=invariant_result,
        supervisor_result=supervisor_result,
        shadow_result=shadow_result,
        adaptations=adaptations,
        source_artifacts=request.source_artifacts,
        production_promotion_allowed=False,
    )
    return RuntimeAssuranceResult(
        evidence_bundle=bundle,
        runtime_mode=supervisor_result.selected_mode,
        generated_at=request.context.observed_at,
    )
