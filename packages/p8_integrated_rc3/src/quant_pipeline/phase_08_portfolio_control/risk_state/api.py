"""Public orchestration API for the complete P8.S4 subphase."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ArtifactRef,
    ModuleReceipt,
)

from .arrays import DependenceArrays, GreekPathArrays, ScenarioPnLCube
from .artifact_store import ArtifactWriter
from .contracts import (
    CandidateSizability,
    DependenceSummary,
    GreekPathSummary,
    LiquiditySummary,
    MarginFundingSummary,
    P8DecisionReadyRiskBundle,
    PnLCubeSummary,
    RiskCapabilityReceipt,
    S4Request,
    S4Result,
)
from .hashing import canonical_sha256
from .modules.dependence import build_dependence
from .modules.greek_path import build_greek_path_state
from .modules.liquidity import build_liquidity_state
from .modules.margin_funding import build_margin_funding_state
from .modules.pnl_cube import build_pnl_cube
from .modules.reconciler import make_bundle, reconcile_risk_state
from .ports import BrokerMarginEstimatorPort, ExecutionRiskEstimatorPort


@dataclass(frozen=True, slots=True)
class _StageState:
    cube: ScenarioPnLCube
    pnl_summary: PnLCubeSummary
    dependence_arrays: DependenceArrays
    dependence: DependenceSummary
    greek_arrays: GreekPathArrays
    greek_path: GreekPathSummary
    liquidity: LiquiditySummary
    margin_funding: MarginFundingSummary
    candidate_sizability: tuple[CandidateSizability, ...]
    capability_receipt: RiskCapabilityReceipt
    bundle: P8DecisionReadyRiskBundle
    receipts: tuple[ModuleReceipt, ...]


def _receipt(
    module_id: str,
    input_value: Any,
    output_value: Any,
    status: str = "PASS",
    reasons: tuple[str, ...] = (),
) -> ModuleReceipt:
    return ModuleReceipt(
        module_id=module_id,
        input_sha256=canonical_sha256(input_value),
        output_sha256=canonical_sha256(output_value),
        status=status,
        reason_codes=reasons,
    )


def _artifact_ref(prefix: str, digest: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{prefix}-{digest[:16]}",
        content_sha256=digest,
        schema_version="1.0.0",
        contract_version="1.0.0",
    )


def _validate_s3_links(request: S4Request) -> None:
    bundle = request.scenario_artifacts
    expected = request.s3_result
    if bundle.full_scenarios_sha256 != expected.full_scenarios.content_sha256:
        raise ValueError("full scenario hash differs from S3 result")
    if bundle.reduced_scenarios_sha256 != expected.reduced_scenarios.content_sha256:
        raise ValueError("reduced scenario hash differs from S3 result")
    if bundle.stress_scenarios_sha256 != expected.stress.stress_content_sha256:
        raise ValueError("stress scenario hash differs from S3 result")


def _pnl_stage(request: S4Request) -> tuple[ScenarioPnLCube, PnLCubeSummary, ModuleReceipt]:
    cube, quality = build_pnl_cube(
        request.scenario_artifacts,
        request.candidates,
        request.factor_definitions,
        request.step_year_fractions,
        request.pnl_policy,
    )
    summary = PnLCubeSummary(
        candidate_count=len(cube.candidate_ids),
        leg_count=len(cube.leg_ids),
        scenario_count=len(cube.scenario_ids),
        stress_scenario_count=len(cube.stress_ids),
        step_count=len(cube.step_labels),
        pnl_semantics=cube.pnl_semantics,
        valuation_quality_by_candidate=quality,
        content_sha256=cube.content_sha256(),
    )
    return cube, summary, _receipt("P8.S4.M01", request.scenario_artifacts, summary)


def _dependence_stage(
    request: S4Request,
    cube: ScenarioPnLCube,
) -> tuple[DependenceArrays, DependenceSummary, ModuleReceipt]:
    arrays, summary = build_dependence(cube, request.dependence_policy)
    status = "PASS" if summary.quality.value == "FULLY_QUALIFIED" else "DEGRADED"
    receipt = _receipt(
        "P8.S4.M02", request.dependence_policy, summary, status, summary.reason_codes,
    )
    return arrays, summary, receipt


def _greek_stage(
    request: S4Request,
    cube: ScenarioPnLCube,
) -> tuple[GreekPathArrays, GreekPathSummary, ModuleReceipt]:
    arrays, summary = build_greek_path_state(
        cube,
        request.candidates,
        request.current_candidate_positions,
        request.physical_positions,
        request.greek_policy,
        request.reconciliation_policy.require_physical_reconciliation,
    )
    status = "PASS" if summary.quality.value == "FULLY_QUALIFIED" else "DEGRADED"
    return arrays, summary, _receipt(
        "P8.S4.M03", request.greek_policy, summary, status, summary.reason_codes,
    )


def _liquidity_stage(
    request: S4Request,
    estimator: ExecutionRiskEstimatorPort | None,
) -> tuple[LiquiditySummary, ModuleReceipt]:
    summary = build_liquidity_state(
        request.candidates,
        request.liquidity_snapshot,
        request.s3_result.ambiguity.liquidity_haircut,
        request.liquidity_policy,
        estimator,
    )
    degraded = any(state.fidelity.value != "FULLY_QUALIFIED" for state in summary.states)
    return summary, _receipt(
        "P8.S4.M04", request.liquidity_policy, summary,
        "DEGRADED" if degraded else "PASS",
    )


def _margin_stage(
    request: S4Request,
    cube: ScenarioPnLCube,
    estimator: BrokerMarginEstimatorPort | None,
) -> tuple[MarginFundingSummary, ModuleReceipt]:
    summary = build_margin_funding_state(
        cube,
        request.candidates,
        request.account_state,
        request.borrow_records,
        request.margin_rules,
        request.s3_result.ambiguity.margin_buffer,
        request.margin_policy,
        estimator,
    )
    degraded = any(state.quality.value != "FULLY_QUALIFIED" for state in summary.candidate_states)
    return summary, _receipt(
        "P8.S4.M05", request.margin_policy, summary,
        "DEGRADED" if degraded else "PASS",
    )


def _risk_bundle_stage(
    request: S4Request,
    cube: ScenarioPnLCube,
    pnl: PnLCubeSummary,
    dep_arrays: DependenceArrays,
    dependence: DependenceSummary,
    greek_arrays: GreekPathArrays,
    greek_path: GreekPathSummary,
    liquidity: LiquiditySummary,
    margin: MarginFundingSummary,
) -> tuple[tuple[CandidateSizability, ...], RiskCapabilityReceipt, P8DecisionReadyRiskBundle, ModuleReceipt]:
    sizability, capability = reconcile_risk_state(
        request.candidates,
        cube,
        pnl.valuation_quality_by_candidate,
        dependence,
        greek_path,
        liquidity,
        margin,
        request.s3_result,
        request.reconciliation_policy.degraded_cap_multiplier,
    )
    references = {
        "pnl_cube": _artifact_ref("pnl-cube", cube.content_sha256()),
        "dependence": _artifact_ref("dependence", dep_arrays.content_sha256()),
        "greek_path": _artifact_ref("greek-path", greek_arrays.content_sha256()),
        "liquidity": _artifact_ref("liquidity", liquidity.content_sha256),
        "margin_funding": _artifact_ref("margin-funding", margin.content_sha256),
    }
    bundle = make_bundle(
        request.run_id, request.cycle_id, request.decision_time,
        request.s3_result, references, sizability, capability,
    )
    status = "NO_ACTION_VALID" if all(item.max_units == 0.0 for item in sizability) else "PASS"
    return sizability, capability, bundle, _receipt(
        "P8.S4.M06", capability, bundle, status, capability.reason_codes,
    )


def _execute_stages(
    request: S4Request,
    execution_estimator: ExecutionRiskEstimatorPort | None,
    margin_estimator: BrokerMarginEstimatorPort | None,
) -> _StageState:
    cube, pnl, r1 = _pnl_stage(request)
    dep_arrays, dependence, r2 = _dependence_stage(request, cube)
    greek_arrays, greek_path, r3 = _greek_stage(request, cube)
    liquidity, r4 = _liquidity_stage(request, execution_estimator)
    margin, r5 = _margin_stage(request, cube, margin_estimator)
    sizability, capability, bundle, r6 = _risk_bundle_stage(
        request, cube, pnl, dep_arrays, dependence,
        greek_arrays, greek_path, liquidity, margin,
    )
    return _StageState(
        cube, pnl, dep_arrays, dependence, greek_arrays, greek_path,
        liquidity, margin, sizability, capability, bundle, (r1, r2, r3, r4, r5, r6),
    )


def _persist_state(state: _StageState, output_dir: Path) -> _StageState:
    writer = ArtifactWriter(output_dir)
    pnl = state.pnl_summary.model_copy(update={"storage_npz": writer.write_pnl_cube(state.cube)})
    dependence = state.dependence.model_copy(
        update={"storage_npz": writer.write_dependence(state.dependence_arrays)}
    )
    greek = state.greek_path.model_copy(
        update={"storage_npz": writer.write_greek_path(state.greek_arrays)}
    )
    writer.write_model("liquidity_state", state.liquidity)
    writer.write_model("margin_funding_state", state.margin_funding)
    writer.write_model("risk_bundle", state.bundle)
    return _StageState(
        state.cube, pnl, state.dependence_arrays, dependence,
        state.greek_arrays, greek, state.liquidity, state.margin_funding,
        state.candidate_sizability, state.capability_receipt, state.bundle, state.receipts,
    )


def _to_result(request: S4Request, state: _StageState) -> S4Result:
    payload = {
        "run_id": request.run_id,
        "cycle_id": request.cycle_id,
        "pnl_cube": state.pnl_summary,
        "dependence": state.dependence,
        "greek_path": state.greek_path,
        "liquidity": state.liquidity,
        "margin_funding": state.margin_funding,
        "candidate_sizability": state.candidate_sizability,
        "risk_capability_receipt": state.capability_receipt,
        "bundle": state.bundle,
        "receipts": state.receipts,
    }
    return S4Result(**payload, result_sha256=canonical_sha256(payload))


def run_s4(
    request: S4Request,
    output_dir: Path | None = None,
    execution_risk_estimator: ExecutionRiskEstimatorPort | None = None,
    broker_margin_estimator: BrokerMarginEstimatorPort | None = None,
) -> S4Result:
    """Run all six S4 modules and optionally persist immutable artifacts."""
    _validate_s3_links(request)
    state = _execute_stages(request, execution_risk_estimator, broker_margin_estimator)
    if output_dir is not None:
        state = _persist_state(state, output_dir)
    result = _to_result(request, state)
    if output_dir is not None:
        ArtifactWriter(output_dir).write_model("s4_result", result)
    return result
