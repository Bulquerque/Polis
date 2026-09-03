"""P9.S8.M08 — hierarchical PnL reconciliation and root-cause evidence graph."""

from __future__ import annotations

from pydantic import Field

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    EvidenceClass,
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import (
    AttributionAmount,
    AttributionQuality,
    CausalStrength,
    EvidenceStrength,
    RootCauseEdge,
    RootCauseNode,
)
from .m01_forecast_attribution import ForecastAttributionResult
from .m02_payoff_attribution import PayoffAttributionResult
from .m03_ranking_attribution import RankingAttributionResult
from .m04_portfolio_attribution import PortfolioAttributionResult
from .m05_execution_attribution import ExecutionAttributionResult
from .m06_option_attribution import OptionAttributionResult
from .m07_counterfactual import CounterfactualPolicyResult


class ReconciliationPolicy(StrictModel):
    absolute_tolerance: float = Field(default=1e-8, ge=0.0)
    material_cause_threshold: float = Field(default=0.0, ge=0.0)
    decomposition_version: NonEmptyStr = "SEQUENTIAL_P5_P8_V1"


class AttributionReconciliationReceipt(StrictModel):
    decomposition_version: NonEmptyStr
    factual_pnl: float
    attributed_pnl: float
    residual_pnl: float
    tolerance: float = Field(ge=0.0)
    reconciled: bool
    double_count_checks_passed: bool
    reason_codes: tuple[NonEmptyStr, ...]


class HierarchicalPnlAttributionResult(StrictModel):
    stage_amounts: tuple[AttributionAmount, ...]
    option_nested_explanation: OptionAttributionResult
    counterfactual_diagnostic: CounterfactualPolicyResult
    reconciliation: AttributionReconciliationReceipt
    root_cause_nodes: tuple[RootCauseNode, ...]
    root_cause_edges: tuple[RootCauseEdge, ...]
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def reconcile_attribution(
    factual_pnl: float,
    forecast: ForecastAttributionResult,
    payoff: PayoffAttributionResult,
    ranking: RankingAttributionResult,
    portfolio: PortfolioAttributionResult,
    execution: ExecutionAttributionResult,
    options: OptionAttributionResult,
    counterfactual: CounterfactualPolicyResult,
    rollback_state: str,
    policy: ReconciliationPolicy,
) -> HierarchicalPnlAttributionResult:
    """Reconcile additive stage effects and build an evidence-limited cause graph.

    Option PnL is nested inside the factual market/lifecycle PnL and counterfactual
    opportunity cost is diagnostic. Neither is added to the stage waterfall.
    """

    stage_amounts = tuple(
        item
        for item in (
            _amount("FORECAST", forecast.aggregate_pnl_effect, forecast.quality),
            _amount("PAYOFF", payoff.aggregate_pnl_effect, payoff.quality),
            _amount("RANKING", ranking.aggregate_pnl_effect, ranking.quality),
            _amount("PORTFOLIO", portfolio.aggregate_pnl_effect, portfolio.quality),
            _amount("EXECUTION_LIFECYCLE", execution.aggregate_pnl_effect, execution.quality),
        )
        if item is not None
    )
    attributed = sum(item.pnl_effect for item in stage_amounts)
    residual = factual_pnl - attributed
    reconciled = abs(residual) <= policy.absolute_tolerance
    reasons: set[str] = set()
    if not reconciled:
        reasons.add("P9_ATTRIBUTION_RECONCILIATION_FAILED")
        reasons.add("P9_ATTRIBUTION_RESIDUAL_MATERIAL")
    double_count_checks = _double_count_checks(options, counterfactual, attributed)
    if not double_count_checks:
        reasons.add("P9_ATTRIBUTION_DOUBLE_COUNT_DETECTED")
    receipt = AttributionReconciliationReceipt(
        decomposition_version=policy.decomposition_version,
        factual_pnl=factual_pnl,
        attributed_pnl=attributed,
        residual_pnl=residual,
        tolerance=policy.absolute_tolerance,
        reconciled=reconciled,
        double_count_checks_passed=double_count_checks,
        reason_codes=tuple(sorted(reasons)),
    )
    nodes, edges = _build_root_cause_graph(
        stage_amounts,
        forecast,
        payoff,
        ranking,
        portfolio,
        execution,
        options,
        counterfactual,
        rollback_state,
        policy,
    )
    if any(node.causal_strength is CausalStrength.UNRESOLVED for node in nodes):
        reasons.add("P9_ATTRIBUTION_ROOT_CAUSE_UNSUPPORTED")
    if not reconciled or not double_count_checks:
        quality = AttributionQuality.INVALID
    elif any(item.quality is not AttributionQuality.QUALIFIED for item in stage_amounts):
        quality = AttributionQuality.LIMITED
    else:
        quality = AttributionQuality.QUALIFIED
    payload = {
        "stage_amounts": [item.model_dump(mode="json") for item in stage_amounts],
        "reconciliation": receipt.model_dump(mode="json"),
        "nodes": [item.model_dump(mode="json") for item in nodes],
        "edges": [item.model_dump(mode="json") for item in edges],
        "quality": quality,
        "reason_codes": sorted(reasons),
    }
    return HierarchicalPnlAttributionResult(
        stage_amounts=stage_amounts,
        option_nested_explanation=options,
        counterfactual_diagnostic=counterfactual,
        reconciliation=receipt,
        root_cause_nodes=nodes,
        root_cause_edges=edges,
        quality=quality,
        reason_codes=tuple(sorted(reasons)),
        result_sha256=payload_sha256(payload),
    )


def _amount(
    component_id: str,
    pnl_effect: float | None,
    quality: AttributionQuality,
) -> AttributionAmount | None:
    if pnl_effect is None:
        return None
    evidence = (
        EvidenceClass.FACTUAL_EXECUTED
        if quality is AttributionQuality.QUALIFIED
        else EvidenceClass.MODEL_BASED_COUNTERFACTUAL
    )
    return AttributionAmount(
        component_id=component_id,
        pnl_effect=pnl_effect,
        evidence_class=evidence,
        quality=quality,
    )


def _double_count_checks(
    options: OptionAttributionResult,
    counterfactual: CounterfactualPolicyResult,
    attributed_pnl: float,
) -> bool:
    del attributed_pnl
    # Nested option explanation and counterfactual opportunity are intentionally
    # absent from stage_amounts. This function becomes the explicit audit hook.
    return options.full_repricing_pnl == options.full_repricing_pnl and (
        counterfactual.opportunity_cost_vs_factual is None
        or counterfactual.opportunity_cost_vs_factual
        == counterfactual.opportunity_cost_vs_factual
    )


def _build_root_cause_graph(
    stage_amounts: tuple[AttributionAmount, ...],
    forecast: ForecastAttributionResult,
    payoff: PayoffAttributionResult,
    ranking: RankingAttributionResult,
    portfolio: PortfolioAttributionResult,
    execution: ExecutionAttributionResult,
    options: OptionAttributionResult,
    counterfactual: CounterfactualPolicyResult,
    rollback_state: str,
    policy: ReconciliationPolicy,
) -> tuple[tuple[RootCauseNode, ...], tuple[RootCauseEdge, ...]]:
    modules = {
        "FORECAST": ("P9.S8.M01", forecast.reason_codes),
        "PAYOFF": ("P9.S8.M02", payoff.reason_codes),
        "RANKING": ("P9.S8.M03", ranking.reason_codes),
        "PORTFOLIO": ("P9.S8.M04", portfolio.reason_codes),
        "EXECUTION_LIFECYCLE": ("P9.S8.M05", execution.reason_codes),
    }
    nodes: list[RootCauseNode] = []
    edges: list[RootCauseEdge] = []
    for amount in stage_amounts:
        if abs(amount.pnl_effect) <= policy.material_cause_threshold:
            continue
        module_id, reason_codes = modules[amount.component_id]
        strength = _causal_strength(amount)
        evidence_strength = _evidence_strength(amount.evidence_class)
        cause_id = f"CAUSE_{amount.component_id}"
        nodes.append(
            RootCauseNode(
                cause_id=cause_id,
                source_module_id=module_id,  # type: ignore[arg-type]
                label=f"{amount.component_id} contribution",
                pnl_effect=amount.pnl_effect,
                causal_strength=strength,
                evidence_strength=evidence_strength,
                evidence_refs=(amount.component_id,),
                reason_codes=tuple(reason_codes),
            )
        )
        edges.append(
            RootCauseEdge(
                parent_cause_id=cause_id,
                child_cause_id="FACTUAL_PNL",
                relation="CONTRIBUTES_TO",
            )
        )
    if options.reason_codes:
        nodes.append(
            RootCauseNode(
                cause_id="CAUSE_OPTION_RESIDUAL",
                source_module_id="P9.S8.M06",
                label="Option full-repricing residual",
                pnl_effect=options.residual_pnl,
                causal_strength=(
                    CausalStrength.PLAUSIBLE
                    if options.quality is AttributionQuality.LIMITED
                    else CausalStrength.SUPPORTED
                ),
                evidence_strength=EvidenceStrength.FACTUAL,
                evidence_refs=(options.result_sha256,),
                reason_codes=options.reason_codes,
            )
        )
    if counterfactual.quality is AttributionQuality.NOT_IDENTIFIABLE:
        nodes.append(
            RootCauseNode(
                cause_id="CAUSE_COUNTERFACTUAL_UNRESOLVED",
                source_module_id="P9.S8.M07",
                label="Counterfactual opportunity unresolved",
                causal_strength=CausalStrength.UNRESOLVED,
                evidence_strength=EvidenceStrength.INSUFFICIENT,
                evidence_refs=(counterfactual.result_sha256,),
                reason_codes=counterfactual.reason_codes,
            )
        )
    if rollback_state not in {"HEALTHY", "INSUFFICIENT_LIVE_EVIDENCE"}:
        nodes.append(
            RootCauseNode(
                cause_id="CAUSE_LIVE_DEGRADATION",
                source_module_id="P9.S8.M08",
                label=f"Prospective state {rollback_state}",
                causal_strength=CausalStrength.PLAUSIBLE,
                evidence_strength=EvidenceStrength.OBSERVABLE,
                evidence_refs=(rollback_state,),
            )
        )
    return tuple(nodes), tuple(edges)


def _causal_strength(amount: AttributionAmount) -> CausalStrength:
    if amount.evidence_class in {
        EvidenceClass.FACTUAL_EXECUTED,
        EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
    } and amount.quality is AttributionQuality.QUALIFIED:
        return CausalStrength.SUPPORTED
    if amount.evidence_class in {
        EvidenceClass.OBSERVABLE_COUNTERFACTUAL,
        EvidenceClass.MODEL_BASED_COUNTERFACTUAL,
    }:
        return CausalStrength.PLAUSIBLE
    return CausalStrength.UNRESOLVED


def _evidence_strength(value: EvidenceClass) -> EvidenceStrength:
    if value is EvidenceClass.FACTUAL_EXECUTED:
        return EvidenceStrength.FACTUAL
    if value in {
        EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
        EvidenceClass.OBSERVABLE_COUNTERFACTUAL,
    }:
        return EvidenceStrength.OBSERVABLE
    if value is EvidenceClass.MODEL_BASED_COUNTERFACTUAL:
        return EvidenceStrength.MODEL_BASED
    return EvidenceStrength.INSUFFICIENT
