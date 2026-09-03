from __future__ import annotations

from datetime import datetime

from .contracts import ModuleReceipt, S6State, content_sha256
from .m01_stress_scenario_taxonomy_and_commitment_registry import build_scenario_registry
from .m02_historical_crisis_replay_and_regime_mapping_engine import replay_historical_crisis
from .m03_factor_shock_and_global_sensitivity_surface_engine import build_sensitivity_surface
from .m04_conditional_extreme_value_tail_engine import fit_conditional_evt
from .m05_distributional_ambiguity_and_worst_case_engine import evaluate_distributional_robustness
from .m06_liquidity_capacity_crowding_and_fire_sale_engine import evaluate_capacity
from .m07_reverse_stress_breakpoint_and_resilience_engine import solve_reverse_stress
from .m08_stress_model_and_scenario_validation_gate import validate_stress_models
from .models import (
    RobustnessStressBundleManifest,
    HistoricalReplayRequest,
    ReverseStressRequest,
    S6OutputBundle,
    S6RunRequest,
    SensitivitySurfaceRequest,
    StressValidationRequest,
)


class S6PipelineError(RuntimeError):
    """Raised when a hard prerequisite blocks integrated S6 execution."""


def _receipt(module_id: str, output: object, status: S6State, at: datetime) -> ModuleReceipt:
    return ModuleReceipt(
        module_id=module_id,
        status=status,
        reason_codes=tuple(getattr(output, "reason_codes", ())),
        limitations=tuple(getattr(output, "limitations", ())),
        output_sha256=content_sha256(output),
        started_at=at,
        completed_at=at,
    )


def _unavailable_receipt(module_id: str, at: datetime, reason: str) -> ModuleReceipt:
    return ModuleReceipt(
        module_id=module_id,
        status=S6State.CAPABILITY_UNAVAILABLE,
        reason_codes=(reason,),
        limitations=("optional specialist capability was not requested",),
        output_sha256=content_sha256(None),
        started_at=at,
        completed_at=at,
    )


def run_s6(request: S6RunRequest) -> S6OutputBundle:
    """Execute P9.S6 while preserving all module boundaries and receipts."""

    context = request.scenario_registry.context
    at = context.decision_time
    receipts: list[ModuleReceipt] = []

    registry = build_scenario_registry(request.scenario_registry)
    receipts.append(_receipt("P9.S6.M01", registry, registry.status, at))
    if registry.status is S6State.INVALID:
        raise S6PipelineError("M01 blocked S6: no valid committed scenarios")

    historical = replay_historical_crisis(
        HistoricalReplayRequest(
            context=context,
            registry=registry,
            scenario_id=request.crisis_scenario_id,
            factor_path=request.crisis_factor_path,
            exposures=request.crisis_exposures,
            mappings=request.crisis_mappings,
            replay_mode=request.crisis_replay_mode,
            frozen_exposure_scales=request.crisis_frozen_exposure_scales,
            policy=request.historical_replay_policy,
        )
    )
    receipts.append(_receipt("P9.S6.M02", historical, historical.status, at))

    sensitivity = build_sensitivity_surface(
        SensitivitySurfaceRequest(
            context=context,
            registry=registry,
            response_model=request.sensitivity_response_model,
            axes=request.sensitivity_axes,
            constraints=request.sensitivity_constraints,
            policy=request.sensitivity_policy,
        )
    )
    receipts.append(_receipt("P9.S6.M03", sensitivity, sensitivity.status, at))

    evt = None
    if request.evt is not None:
        evt = fit_conditional_evt(request.evt)
        receipts.append(_receipt("P9.S6.M04", evt, evt.status, at))
    else:
        receipts.append(
            _unavailable_receipt(
                "P9.S6.M04", at, "P9_STRESS_SPECIALIST_CAPABILITY_UNAVAILABLE"
            )
        )

    dro = None
    if request.dro is not None:
        dro = evaluate_distributional_robustness(request.dro)
        receipts.append(_receipt("P9.S6.M05", dro, dro.status, at))
    else:
        receipts.append(
            _unavailable_receipt(
                "P9.S6.M05", at, "P9_STRESS_SPECIALIST_CAPABILITY_UNAVAILABLE"
            )
        )

    capacity = evaluate_capacity(request.capacity)
    receipts.append(_receipt("P9.S6.M06", capacity, capacity.status, at))

    reverse = solve_reverse_stress(
        ReverseStressRequest(
            context=context,
            response_model=request.sensitivity_response_model,
            bounds=request.reverse_bounds,
            failure_condition=request.reverse_failure_condition,
            seed_policy=request.reverse_seed_policy,
            policy=request.reverse_policy,
        )
    )
    receipts.append(_receipt("P9.S6.M07", reverse, reverse.status, at))

    validation = validate_stress_models(
        StressValidationRequest(
            context=context,
            registry=registry,
            historical_replay=historical,
            sensitivity=sensitivity,
            evt=evt,
            dro=dro,
            capacity=capacity,
            reverse_stress=reverse,
            policy=request.validation_policy,
        )
    )
    receipts.append(_receipt("P9.S6.M08", validation, validation.status, at))

    payload = {
        "context": context.model_dump(mode="json"),
        "registry": content_sha256(registry),
        "historical": content_sha256(historical),
        "sensitivity": content_sha256(sensitivity),
        "evt": content_sha256(evt),
        "dro": content_sha256(dro),
        "capacity": content_sha256(capacity),
        "reverse": content_sha256(reverse),
        "validation": content_sha256(validation),
        "receipts": [content_sha256(receipt) for receipt in receipts],
    }
    bundle_hash = content_sha256(payload)
    return S6OutputBundle(
        bundle_id=f"{context.run_id}:P9.S6:{bundle_hash[:16]}",
        context=context,
        scenario_registry=registry,
        historical_replay=historical,
        sensitivity=sensitivity,
        evt=evt,
        dro=dro,
        capacity=capacity,
        reverse_stress=reverse,
        validation=validation,
        module_receipts=tuple(receipts),
        bundle_sha256=bundle_hash,
    )


def build_robustness_stress_manifest(
    s5_bundle_sha256: str,
    s5_qualification_status: str,
    s6_bundle: S6OutputBundle,
) -> RobustnessStressBundleManifest:
    payload = {
        "run_id": s6_bundle.context.run_id,
        "cycle_id": s6_bundle.context.cycle_id,
        "s5_bundle_sha256": s5_bundle_sha256,
        "s6_bundle_sha256": s6_bundle.bundle_sha256,
        "s5_qualification_status": s5_qualification_status,
        "s6_validation_status": s6_bundle.validation.status,
    }
    digest = content_sha256(payload)
    return RobustnessStressBundleManifest(
        manifest_id=f"{s6_bundle.context.run_id}:S5S6:{digest[:16]}",
        run_id=s6_bundle.context.run_id,
        cycle_id=s6_bundle.context.cycle_id,
        s5_bundle_sha256=s5_bundle_sha256,
        s6_bundle_sha256=s6_bundle.bundle_sha256,
        s5_qualification_status=s5_qualification_status,
        s6_validation_status=s6_bundle.validation.status,
        manifest_sha256=digest,
    )
