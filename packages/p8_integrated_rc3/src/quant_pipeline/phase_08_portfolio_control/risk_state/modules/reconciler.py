"""P8.S4.M06 joint risk-state reconciler and Agent-3 bundle builder."""
from __future__ import annotations

import math
from datetime import datetime

from ..arrays import ScenarioPnLCube
from ..contracts import (
    ArtifactRef,
    CandidateEconomicPackage,
    CandidateMarginState,
    CandidateSizability,
    ComponentQuality,
    ConsumptionStatus,
    DependenceSummary,
    GreekPathSummary,
    LiquiditySummary,
    MarginFundingSummary,
    P8DecisionReadyRiskBundle,
    RiskCapabilityReceipt,
    S3Result,
    SizabilityState,
    ValuationQuality,
)
from ..hashing import canonical_sha256

MODULE_ID = "P8.S4.M06"


def _actionability_blocks_new_risk(s3_result: S3Result) -> bool:
    return s3_result.ambiguity.actionability_state.value in {
        "NO_ACTION_VALID", "NO_NEW_RISK", "CLOSE_ONLY",
    }


def _finite_capacity(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return max(value, 0.0)


def _component_quality(
    candidate_id: str,
    valuation_quality: dict[str, ValuationQuality],
    dependence: DependenceSummary,
    greek_path: GreekPathSummary,
    liquidity_state,
    margin_state: CandidateMarginState,
) -> dict[str, ComponentQuality]:
    valuation = (
        ComponentQuality.FULLY_QUALIFIED
        if valuation_quality.get(candidate_id) in {
            ValuationQuality.FULL_REPRICING, ValuationQuality.ANALYTIC_LINEAR,
        }
        else ComponentQuality.UNAVAILABLE
    )
    return {
        "valuation": valuation,
        "dependence": dependence.quality,
        "greek_path": greek_path.quality,
        "liquidity": liquidity_state.fidelity,
        "margin": margin_state.quality,
        "capital_funding": margin_state.capital_quality,
    }


def _incomplete_candidate(candidate_id: str, risk_cap: float) -> CandidateSizability:
    return CandidateSizability(
        candidate_id=candidate_id,
        state=SizabilityState.RISK_STATE_INCOMPLETE,
        risk_budget_cap=risk_cap,
        component_quality={"risk_state": ComponentQuality.UNAVAILABLE},
        reason_codes=("CANDIDATE_MISSING_FROM_RISK_STATE",),
    )


def _candidate_sizability(
    candidate: CandidateEconomicPackage,
    cube: ScenarioPnLCube,
    valuation_quality: dict[str, ValuationQuality],
    dependence: DependenceSummary,
    greek_path: GreekPathSummary,
    liquidity_state,
    margin_state: CandidateMarginState,
    s3_result: S3Result,
    degraded_cap_multiplier: float,
) -> CandidateSizability:
    components = _component_quality(
        candidate.candidate_id, valuation_quality, dependence,
        greek_path, liquidity_state, margin_state,
    )
    liquidity_capacity = _finite_capacity(liquidity_state.capacity_units)
    capital_capacity = _finite_capacity(margin_state.capital_capacity_units)
    reasons: list[str] = []
    blocked = _actionability_blocks_new_risk(s3_result)
    if blocked:
        reasons.append(s3_result.ambiguity.actionability_state.value)
    if liquidity_capacity is None or liquidity_state.fidelity == ComponentQuality.UNAVAILABLE:
        reasons.extend(liquidity_state.reason_codes or ("LIQUIDITY_CAPACITY_UNAVAILABLE",))
    if capital_capacity is None or margin_state.capital_quality == ComponentQuality.UNAVAILABLE:
        reasons.extend(margin_state.reason_codes or ("MARGIN_MODEL_UNAVAILABLE",))
    unavailable = any(
        value in {ComponentQuality.UNAVAILABLE, ComponentQuality.REJECTED}
        for value in components.values()
    )
    if blocked or unavailable or liquidity_capacity is None or capital_capacity is None:
        state = SizabilityState.NOT_SIZABLE
        max_units = 0.0
    else:
        cap = s3_result.ambiguity.risk_budget_cap
        degraded = any(value == ComponentQuality.DEGRADED for value in components.values())
        if degraded:
            cap *= degraded_cap_multiplier
            state = SizabilityState.DEGRADED_SIZABLE
            reasons.append("DEGRADED_COMPONENT_CAP_APPLIED")
        else:
            state = SizabilityState.FULLY_SIZABLE
        max_units = max(min(liquidity_capacity, capital_capacity) * cap, 0.0)
    return CandidateSizability(
        candidate_id=candidate.candidate_id,
        state=state,
        max_units=max_units,
        liquidity_max_units=liquidity_capacity,
        capital_max_units=capital_capacity,
        risk_budget_cap=s3_result.ambiguity.risk_budget_cap,
        component_quality=components,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def _capability_receipt(
    output: tuple[CandidateSizability, ...],
) -> RiskCapabilityReceipt:
    artifacts = {
        name: ConsumptionStatus.SEMANTICALLY_CONSUMED
        for name in (
            "S3_SCENARIOS", "S3_STRESSES", "S3_AMBIGUITY",
            "SCENARIO_PNL_CUBE", "DEPENDENCE_STATE", "GREEK_PATH_STATE",
            "LIQUIDITY_STATE", "MARGIN_FUNDING_STATE",
        )
    }
    return RiskCapabilityReceipt(
        artifact_status=artifacts,
        candidate_status={item.candidate_id: item.state for item in output},
        reason_codes=tuple(sorted({reason for item in output for reason in item.reason_codes})),
    )


def reconcile_risk_state(
    candidates: tuple[CandidateEconomicPackage, ...],
    cube: ScenarioPnLCube,
    valuation_quality: dict[str, ValuationQuality],
    dependence: DependenceSummary,
    greek_path: GreekPathSummary,
    liquidity: LiquiditySummary,
    margin_funding: MarginFundingSummary,
    s3_result: S3Result,
    degraded_cap_multiplier: float,
) -> tuple[tuple[CandidateSizability, ...], RiskCapabilityReceipt]:
    liquidity_map = {state.candidate_id: state for state in liquidity.states}
    margin_map = {state.candidate_id: state for state in margin_funding.candidate_states}
    output: list[CandidateSizability] = []
    for candidate in candidates:
        liquidity_state = liquidity_map.get(candidate.candidate_id)
        margin_state = margin_map.get(candidate.candidate_id)
        if liquidity_state is None or margin_state is None or candidate.candidate_id not in cube.candidate_ids:
            output.append(_incomplete_candidate(
                candidate.candidate_id, s3_result.ambiguity.risk_budget_cap,
            ))
            continue
        output.append(_candidate_sizability(
            candidate, cube, valuation_quality, dependence, greek_path,
            liquidity_state, margin_state, s3_result, degraded_cap_multiplier,
        ))
    result = tuple(output)
    return result, _capability_receipt(result)


def make_bundle(
    run_id: str,
    cycle_id: str,
    decision_time: datetime,
    s3_result: S3Result,
    references: dict[str, ArtifactRef],
    sizability: tuple[CandidateSizability, ...],
    receipt: RiskCapabilityReceipt,
) -> P8DecisionReadyRiskBundle:
    payload = {
        "bundle_id": f"P8-RISK-{run_id}-{cycle_id}",
        "run_id": run_id,
        "cycle_id": cycle_id,
        "decision_time": decision_time,
        "s3_result_sha256": s3_result.result_sha256,
        "pnl_cube_ref": references["pnl_cube"],
        "dependence_state_ref": references["dependence"],
        "greek_path_state_ref": references["greek_path"],
        "liquidity_state_ref": references["liquidity"],
        "margin_funding_state_ref": references["margin_funding"],
        "candidate_sizability": sizability,
        "risk_capability_receipt": receipt,
    }
    return P8DecisionReadyRiskBundle(**payload, content_sha256=canonical_sha256(payload))
