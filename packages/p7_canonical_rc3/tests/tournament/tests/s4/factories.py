from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.artifacts import build_artifact
from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.input_records import (
    ComparableMetricRecord,
    ComparisonGroupRecord,
    DominanceEvidence,
    DominanceRelationRecord,
    DominanceSurvivorRecord,
    DominatedCandidateRecord,
    FactorAdjustedMetricRecord,
    FactorAdjustmentAuditRecord,
    FactorExposureRecord,
    MetricSemanticsAuditRecord,
    ParetoFrontierAuditRecord,
    ParetoFrontierRecord,
    ParetoGroupDiagnostic,
)
from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.policy_records import (
    HeadPolicy,
    MetricBindingPolicy,
    PenaltyRule,
    ScoringPolicyContextRecord,
    ScoringPolicyRule,
)
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.enums import (
    AdjustmentStatus,
    ComparisonStatus,
    Direction,
    FrontierStatus,
    MetricSourcePreference,
    MissingHeadAction,
    MissingMetricAction,
    NormalizationMethod,
    SmallGroupAction,
    TransformationMethod,
)
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.serialization import sha256_hex

DECISION_TIME = datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)
RUN_ID = "run-s4-fixture-001"
CYCLE_ID = "cycle-s4-fixture-001"


def _artifact(name: str, records: tuple[Any, ...], module: str = "P7.S3.M04", *, available_at: datetime = DECISION_TIME) -> dict[str, Any]:
    artifact = build_artifact(
        artifact_name=name,
        schema_version="1.0.0",
        producer_module_id=module,
        run_id=RUN_ID,
        cycle_id=CYCLE_ID,
        decision_time=DECISION_TIME,
        execution_time=available_at,
        lineage_id=f"lineage:{name}",
        records=records,
    )
    return artifact.model_dump(mode="json")


def _metric_binding(
    metric_id: str,
    *,
    normalization: NormalizationMethod = NormalizationMethod.IDENTITY_BOUNDED,
    absolute_lower: float | None = 0.0,
    absolute_upper: float | None = 1.0,
    source: MetricSourcePreference = MetricSourcePreference.COMPARABLE_ONLY,
    missing: MissingMetricAction = MissingMetricAction.BLOCK_HEAD,
    missing_penalty: float = 0.0,
    min_group_size: int = 2,
    small_group: SmallGroupAction = SmallGroupAction.ABSOLUTE_FALLBACK,
) -> MetricBindingPolicy:
    return MetricBindingPolicy(
        metric_id=metric_id,
        source_preference=source,
        transformation=TransformationMethod.IDENTITY,
        normalization=normalization,
        metric_weight=1.0,
        absolute_lower=absolute_lower,
        absolute_upper=absolute_upper,
        min_group_size=min_group_size,
        small_group_action=small_group,
        missing_metric_action=missing,
        missing_metric_penalty=missing_penalty,
    )


def scoring_rule(
    *,
    rule_id: str = "rule-range-5d",
    objective_families: tuple[str, ...] = ("RANGE",),
    horizons: tuple[str, ...] = ("5D",),
    max_layer: int = 0,
    confidence_strength: float = 0.25,
    missing_edge: MissingMetricAction = MissingMetricAction.BLOCK_HEAD,
    edge_missing_penalty: float = 0.0,
    small_group: SmallGroupAction = SmallGroupAction.ABSOLUTE_FALLBACK,
) -> ScoringPolicyRule:
    heads = (
        HeadPolicy(
            head_id="BELIEF_FIT", head_weight=0.15,
            missing_head_action=MissingHeadAction.BLOCK,
            metric_bindings=(_metric_binding("belief_fit"),),
        ),
        HeadPolicy(
            head_id="ECONOMIC_EDGE", head_weight=0.25,
            missing_head_action=MissingHeadAction.BLOCK,
            metric_bindings=(
                _metric_binding(
                    "expected_net_payoff",
                    normalization=NormalizationMethod.PERCENTILE,
                    absolute_lower=0.0,
                    absolute_upper=20.0,
                    source=MetricSourcePreference.FACTOR_ADJUSTED_PREFERRED,
                    missing=missing_edge,
                    missing_penalty=edge_missing_penalty,
                    small_group=small_group,
                ),
            ),
        ),
        HeadPolicy(
            head_id="DOWNSIDE_SAFETY", head_weight=0.15,
            missing_head_action=MissingHeadAction.BLOCK,
            metric_bindings=(
                _metric_binding("expected_shortfall", normalization=NormalizationMethod.ABSOLUTE_RANGE, absolute_lower=-20.0, absolute_upper=0.0),
            ),
        ),
        HeadPolicy(
            head_id="CONVEXITY_ASYMMETRY", head_weight=0.10,
            missing_head_action=MissingHeadAction.RENORMALIZE_ALLOWED,
            metric_bindings=(_metric_binding("convexity_quality", missing=MissingMetricAction.RENORMALIZE_METRICS),),
        ),
        HeadPolicy(
            head_id="EXECUTION_QUALITY", head_weight=0.15,
            missing_head_action=MissingHeadAction.PENALIZE,
            missing_head_penalty=0.1,
            metric_bindings=(_metric_binding("liquidity_quality"),),
        ),
        HeadPolicy(
            head_id="ROBUSTNESS_CONFIDENCE", head_weight=0.15,
            missing_head_action=MissingHeadAction.BLOCK,
            metric_bindings=(_metric_binding("robustness_confidence"),),
        ),
        HeadPolicy(
            head_id="SIMPLICITY_PARSIMONY", head_weight=0.05,
            missing_head_action=MissingHeadAction.RENORMALIZE_ALLOWED,
            metric_bindings=(
                _metric_binding("complexity_cost", normalization=NormalizationMethod.ABSOLUTE_RANGE, absolute_lower=-10.0, absolute_upper=0.0),
            ),
        ),
    )
    return ScoringPolicyRule(
        rule_id=rule_id,
        operational_modes=("BASELINE",),
        objective_families=objective_families,
        horizons=horizons,
        max_frontier_layer=max_layer,
        include_incomparable=False,
        heads=heads,
        penalty_rules=(
            PenaltyRule(penalty_id="downside-floor", head_id="DOWNSIDE_SAFETY", threshold=0.30, coefficient=0.20),
            PenaltyRule(penalty_id="execution-floor", head_id="EXECUTION_QUALITY", threshold=0.30, coefficient=0.10),
        ),
        confidence_head_id="ROBUSTNESS_CONFIDENCE",
        confidence_shrinkage_strength=confidence_strength,
    )


def scoring_policy(*, rules: tuple[ScoringPolicyRule, ...] | None = None) -> ScoringPolicyContextRecord:
    return ScoringPolicyContextRecord(
        policy_id="p7-s4-scoring-v1",
        policy_version="1.0.0",
        operational_mode="BASELINE",
        rules=rules or (scoring_rule(),),
        forbidden_field_names=(
            "future_return", "realized_return", "realized_pnl", "outcome", "target_return",
            "rank", "portfolio_weight", "execution_price", "fill_price",
        ),
    )


def make_bundle(
    *,
    reverse_records: bool = False,
    separate_c_group: bool = False,
    missing_metric: tuple[str, str] | None = None,
    policy: ScoringPolicyContextRecord | None = None,
    policy_available_at: datetime = DECISION_TIME,
    value_overrides: dict[tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    groups = (
        ComparisonGroupRecord(candidate_id="A", comparison_group_id="group-1", underlying_id="XYZ", horizon="5D", objective_family="RANGE", capital_at_risk_bucket="SMALL", lineage_id="candidate:A"),
        ComparisonGroupRecord(candidate_id="B", comparison_group_id="group-1", underlying_id="XYZ", horizon="5D", objective_family="RANGE", capital_at_risk_bucket="SMALL", lineage_id="candidate:B"),
        ComparisonGroupRecord(candidate_id="C", comparison_group_id="group-2" if separate_c_group else "group-1", underlying_id="XYZ", horizon="5D", objective_family="RANGE", capital_at_risk_bucket="SMALL", lineage_id="candidate:C"),
    )
    values = {
        "A": {"belief_fit": 0.80, "expected_net_payoff": 12.0, "expected_shortfall": -5.0, "convexity_quality": 0.70, "liquidity_quality": 0.80, "robustness_confidence": 0.90, "complexity_cost": -2.0},
        "B": {"belief_fit": 0.60, "expected_net_payoff": 10.0, "expected_shortfall": -6.0, "convexity_quality": 0.40, "liquidity_quality": 0.70, "robustness_confidence": 0.60, "complexity_cost": -2.0},
        "C": {"belief_fit": 0.90, "expected_net_payoff": 15.0, "expected_shortfall": -9.0, "convexity_quality": 0.90, "liquidity_quality": 0.90, "robustness_confidence": 0.70, "complexity_cost": -4.0},
    }
    for key, value in (value_overrides or {}).items():
        values[key[0]][key[1]] = value
    comparable: list[ComparableMetricRecord] = []
    adjusted: list[FactorAdjustedMetricRecord] = []
    for group in groups:
        for metric_id, value in values[group.candidate_id].items():
            if missing_metric == (group.candidate_id, metric_id):
                continue
            comparable.append(
                ComparableMetricRecord(
                    candidate_id=group.candidate_id,
                    comparison_group_id=group.comparison_group_id,
                    metric_id=metric_id,
                    raw_value=value,
                    canonical_value=value,
                    directed_value=value,
                    canonical_units="normalized" if metric_id not in {"expected_net_payoff", "expected_shortfall", "complexity_cost"} else "currency",
                    direction=Direction.MAXIMIZE,
                    semantic_version="1.0.0",
                    source_artifact_id="p6:strategy-risk-panel",
                    source_available_at=DECISION_TIME,
                    missingness_status="AVAILABLE",
                    comparison_status=ComparisonStatus.AVAILABLE,
                    reason_code=None,
                    lineage_id=f"metric:{group.candidate_id}:{metric_id}",
                )
            )
            adjusted.append(
                FactorAdjustedMetricRecord(
                    candidate_id=group.candidate_id,
                    comparison_group_id=group.comparison_group_id,
                    metric_id=metric_id,
                    raw_value=value,
                    directed_value=value,
                    adjusted_raw_value=value,
                    adjusted_directed_value=value,
                    adjustment_status=AdjustmentStatus.ADJUSTED if metric_id == "expected_net_payoff" else AdjustmentStatus.NOT_APPLICABLE,
                    adjustment_model_id="factor-model-v1" if metric_id == "expected_net_payoff" else None,
                    total_factor_contribution=0.0 if metric_id == "expected_net_payoff" else None,
                    intercept=0.0 if metric_id == "expected_net_payoff" else None,
                    reason_code=None,
                    lineage_id=f"adjusted:{group.candidate_id}:{metric_id}",
                )
            )
    relation = DominanceRelationRecord(
        comparison_group_id="group-1",
        dominator_candidate_id="A",
        dominated_candidate_id="B",
        evidence=(DominanceEvidence(metric_id="expected_net_payoff", dominator_value=12.0, dominated_value=10.0, tolerance=0.0, materially_better=True),),
        policy_id="p7-s3-policy-v1",
        relation_hash=sha256_hex({"A": "B"}),
    )
    frontiers = (
        ParetoFrontierRecord(candidate_id="A", comparison_group_id="group-1", frontier_layer=0, frontier_status=FrontierStatus.FRONTIER, dominated_by_count=0, metric_vector_hash=sha256_hex("A"), policy_id="p7-s3-policy-v1", lineage_id="candidate:A"),
        ParetoFrontierRecord(candidate_id="B", comparison_group_id="group-1", frontier_layer=1, frontier_status=FrontierStatus.DOMINATED_LAYER, dominated_by_count=1, metric_vector_hash=sha256_hex("B"), policy_id="p7-s3-policy-v1", lineage_id="candidate:B"),
        ParetoFrontierRecord(candidate_id="C", comparison_group_id="group-2" if separate_c_group else "group-1", frontier_layer=0, frontier_status=FrontierStatus.FRONTIER, dominated_by_count=0, metric_vector_hash=sha256_hex("C"), policy_id="p7-s3-policy-v1", lineage_id="candidate:C"),
    )
    records = {
        "candidate_comparison_group_panel": groups,
        "comparable_candidate_metric_panel": tuple(comparable),
        "factor_adjusted_metric_panel": tuple(adjusted),
        "factor_exposure_panel": (
            FactorExposureRecord(candidate_id="A", comparison_group_id="group-1", factor_id="delta", exposure_value=0.1, coefficient=0.02, contribution=0.002, model_id="factor-model-v1", factor_schema_version="v1", lineage_id="candidate:A"),
            FactorExposureRecord(candidate_id="C", comparison_group_id="group-2" if separate_c_group else "group-1", factor_id="delta", exposure_value=0.2, coefficient=0.02, contribution=0.004, model_id="factor-model-v1", factor_schema_version="v1", lineage_id="candidate:C"),
        ),
        "dominance_relation_panel": (relation,),
        "dominated_candidate_panel": (DominatedCandidateRecord(candidate_id="B", comparison_group_id="group-1", status="DOMINATED", dominator_candidate_ids=("A",), incoming_relation_count=1, lineage_id="candidate:B"),),
        "dominance_survivor_panel": (
            DominanceSurvivorRecord(candidate_id="A", comparison_group_id="group-1", status="SURVIVOR", eligible_for_pareto=True, reason_code=None, lineage_id="candidate:A"),
            DominanceSurvivorRecord(candidate_id="C", comparison_group_id="group-2" if separate_c_group else "group-1", status="SURVIVOR", eligible_for_pareto=True, reason_code=None, lineage_id="candidate:C"),
        ),
        "pareto_frontier_panel": frontiers,
        "metric_semantics_audit_report": (MetricSemanticsAuditRecord(policy_id="p7-s3-policy-v1", candidate_count=3, source_metric_count=len(comparable), output_metric_count=len(comparable), converted_metric_count=0, blocked_metric_count=0, unavailable_metric_count=0, forbidden_field_scan_passed=True, duplicate_grain_count=0, reason_counts={}),),
        "factor_adjustment_audit_report": (FactorAdjustmentAuditRecord(policy_id="p7-s3-policy-v1", mode="QUALIFIED_RESIDUAL", model_id="factor-model-v1", model_status="QUALIFIED", target_metric_id="expected_net_payoff", adjusted_candidate_count=3, bypassed_candidate_count=0, unavailable_candidate_count=0, blocked_candidate_count=0, conservation_max_abs_error=0.0, reason_counts={}),),
        "pareto_frontier_audit_report": (ParetoFrontierAuditRecord(policy_id="p7-s3-policy-v1", exact_algorithm=True, group_count=2 if separate_c_group else 1, candidate_count=3, frontier_count=2, incomparable_count=0, diagnostics=(ParetoGroupDiagnostic(comparison_group_id="group-1", candidate_count=2 if separate_c_group else 3, comparable_candidate_count=2 if separate_c_group else 3, incomparable_candidate_count=0, relation_count=1, layer_count=2, pair_comparisons=3),), permutation_invariant_serialization=True),),
    }
    bundle = {
        name: _artifact(name, tuple(reversed(rows)) if reverse_records else rows)
        for name, rows in records.items()
    }
    bundle["scoring_policy_context"] = _artifact(
        "scoring_policy_context", (policy or scoring_policy(),), module="P7.S2.M04", available_at=policy_available_at
    )
    return bundle


def execution_config() -> dict[str, Any]:
    return {
        "execution_time": DECISION_TIME.isoformat(),
        "strict_hash_validation": True,
        "emit_debug_events": True,
        "numerical_tolerance": 1e-10,
    }


def tamper_artifact(bundle: dict[str, Any], artifact_name: str, path: tuple[str | int, ...], value: Any) -> dict[str, Any]:
    output = deepcopy(bundle)
    current: Any = output[artifact_name]
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    return output


def future_policy_bundle() -> dict[str, Any]:
    return make_bundle(policy_available_at=DECISION_TIME + timedelta(seconds=1))


def replace_artifact_records(bundle: dict[str, Any], artifact_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    output = deepcopy(bundle)
    old = output[artifact_name]
    from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.artifacts import ArtifactEnvelope
    from quant_pipeline.phase_07_strategy_tournament.tournament.domain.serialization import sha256_hex
    payload = {
        "artifact_name": old["artifact_name"],
        "schema_version": old["schema_version"],
        "producer_phase": old["producer_phase"],
        "producer_module_id": old["producer_module_id"],
        "run_id": old["run_id"],
        "cycle_id": old["cycle_id"],
        "decision_time": old["decision_time"],
        "available_at": old["available_at"],
        "lineage_id": old["lineage_id"],
        "records": records,
    }
    digest = sha256_hex(payload)
    old["records"] = records
    old["record_count"] = len(records)
    old["content_sha256"] = digest
    old["artifact_id"] = f"{artifact_name}:{digest[:24]}"
    import json
    ArtifactEnvelope[Any].model_validate_json(json.dumps(old, sort_keys=True, allow_nan=False))
    return output
