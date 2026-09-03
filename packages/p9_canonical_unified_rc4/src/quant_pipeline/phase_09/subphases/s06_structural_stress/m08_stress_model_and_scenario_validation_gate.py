from __future__ import annotations

from .contracts import CapabilityState, S6State
from .models import (
    ApprovedUseDecision,
    StressCheck,
    StressModelValidationResult,
    StressValidationRequest,
)


def _check(check_id: str, passed: bool, detail: str) -> StressCheck:
    return StressCheck(check_id=check_id, passed=passed, detail=detail)


def _capacity_monotonic(request: StressValidationRequest) -> bool:
    tolerance = request.policy.monotonicity_tolerance
    return all(
        right.annual_cost_fraction + tolerance >= left.annual_cost_fraction
        for left, right in zip(request.capacity.points, request.capacity.points[1:])
    )


def _specialist_states(
    request: StressValidationRequest,
) -> tuple[tuple[str, CapabilityState], ...]:
    evt_state = (
        CapabilityState.UNAVAILABLE
        if request.evt is None
        else request.evt.capability_state
    )
    dro_state = (
        CapabilityState.UNAVAILABLE
        if request.dro is None
        else request.dro.capability_state
    )
    return (("EVT", evt_state), ("DRO", dro_state))


def _specialist_available(request: StressValidationRequest) -> tuple[bool, bool]:
    states = dict(_specialist_states(request))
    acceptable = {CapabilityState.AVAILABLE, CapabilityState.LIMITED}
    return states["EVT"] in acceptable, states["DRO"] in acceptable


def _build_checks(request: StressValidationRequest) -> tuple[StressCheck, ...]:
    reverse_ok = request.reverse_stress.status not in {
        S6State.SEARCH_NOT_CONVERGED,
        S6State.INVALID,
    }
    if request.reverse_stress.verification_error is not None:
        reverse_ok = reverse_ok and (
            request.reverse_stress.verification_error
            <= request.policy.maximum_reverse_verification_error
        )
    reverse_distance_ok = (
        request.reverse_stress.distance_to_failure is None
        or request.reverse_stress.distance_to_failure
        >= request.policy.minimum_reverse_distance
    )
    evt_ok, dro_ok = _specialist_available(request)
    return (
        _check(
            "material-risk-coverage",
            request.registry.weighted_material_risk_coverage
            >= request.policy.minimum_material_risk_coverage,
            f"coverage={request.registry.weighted_material_risk_coverage:.6f}",
        ),
        _check(
            "historical-mapping-share",
            request.historical_replay.mapped_exposure_share
            >= request.policy.minimum_mapped_exposure_share,
            f"mapped_share={request.historical_replay.mapped_exposure_share:.6f}",
        ),
        _check(
            "historical-modelled-pnl-share",
            request.historical_replay.modelled_pnl_share
            <= request.policy.maximum_modelled_pnl_share,
            f"modelled_share={request.historical_replay.modelled_pnl_share:.6f}",
        ),
        _check(
            "surface-has-points",
            bool(request.sensitivity.points),
            f"point_count={len(request.sensitivity.points)}",
        ),
        _check(
            "capacity-cost-monotonicity",
            _capacity_monotonic(request),
            "annual cost fraction must not decrease as AUM rises",
        ),
        _check(
            "capacity-applicable",
            request.capacity.status
            not in {S6State.INSUFFICIENT_LIQUIDITY_DATA, S6State.INVALID},
            f"status={request.capacity.status}",
        ),
        _check(
            "reverse-forward-verification",
            reverse_ok,
            (
                f"status={request.reverse_stress.status}, "
                f"error={request.reverse_stress.verification_error}"
            ),
        ),
        _check(
            "reverse-distance",
            reverse_distance_ok,
            f"distance={request.reverse_stress.distance_to_failure}",
        ),
        _check(
            "evt-capability",
            evt_ok or not request.policy.require_evt,
            "EVT is optional unless required by validation policy",
        ),
        _check(
            "dro-capability",
            dro_ok or not request.policy.require_dro,
            "DRO is optional unless required by validation policy",
        ),
    )


def _reasons_and_limits(
    request: StressValidationRequest,
    checks: tuple[StressCheck, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    limitations: list[str] = []
    if not checks[0].passed:
        reasons.append("P9_STRESS_SCENARIO_COVERAGE_GAP")
    if not checks[1].passed or not checks[2].passed:
        reasons.append("P9_STRESS_EVIDENCE_CLASS_MIXED")
    if not checks[4].passed:
        reasons.append("P9_STRESS_CAPACITY_MONOTONICITY_FAILED")
    if not checks[6].passed or not checks[7].passed:
        reasons.append("P9_STRESS_REVERSE_FORWARD_VERIFICATION_FAILED")
    evt_ok, dro_ok = _specialist_available(request)
    if not evt_ok:
        limitations.append("EVT is unavailable or limited for this run")
        reasons.append("P9_STRESS_SPECIALIST_CAPABILITY_UNAVAILABLE")
    if not dro_ok:
        limitations.append("DRO is unavailable or research-only for this run")
        reasons.append("P9_STRESS_SPECIALIST_CAPABILITY_UNAVAILABLE")
    return tuple(dict.fromkeys(reasons)), tuple(limitations)


def _validation_status(
    request: StressValidationRequest,
    checks: tuple[StressCheck, ...],
    limitations: tuple[str, ...],
) -> S6State:
    evt_ok, dro_ok = _specialist_available(request)
    if any(not check.passed for check in checks[:8]):
        return S6State.MODEL_NOT_FIT_FOR_STRESS
    if (request.policy.require_evt and not evt_ok) or (
        request.policy.require_dro and not dro_ok
    ):
        return S6State.UNVALIDATED
    if limitations:
        return S6State.VALIDATED_WITH_LIMITATIONS
    return S6State.VALIDATED


def _approved_uses(
    status: S6State,
    reasons: tuple[str, ...],
) -> tuple[ApprovedUseDecision, ...]:
    promotion_support = status in {
        S6State.VALIDATED,
        S6State.VALIDATED_WITH_LIMITATIONS,
    }
    return (
        ApprovedUseDecision(
            use_id="RESEARCH",
            approved=status is not S6State.INVALID,
        ),
        ApprovedUseDecision(
            use_id="QUALIFICATION",
            approved=promotion_support,
        ),
        ApprovedUseDecision(
            use_id="PROMOTION_SUPPORT",
            approved=status is S6State.VALIDATED,
            reason_codes=() if status is S6State.VALIDATED else reasons,
        ),
    )


def validate_stress_models(
    request: StressValidationRequest,
) -> StressModelValidationResult:
    """Independently validate S6 outputs without recomputing producer algorithms."""

    checks = _build_checks(request)
    reasons, limitations = _reasons_and_limits(request, checks)
    status = _validation_status(request, checks, limitations)
    return StressModelValidationResult(
        status=status,
        checks=checks,
        approved_uses=_approved_uses(status, reasons),
        material_risk_coverage=request.registry.weighted_material_risk_coverage,
        failed_check_count=sum(not check.passed for check in checks),
        specialist_capability_states=_specialist_states(request),
        reason_codes=reasons,
        limitations=limitations,
    )
