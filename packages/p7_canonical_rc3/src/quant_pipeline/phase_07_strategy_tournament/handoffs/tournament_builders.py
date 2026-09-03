from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .common import artifact_records, candidate_index, parse_timestamp


def _candidate_records(eligible_rows: list[dict[str, Any]], group_rows: list[dict[str, Any]]):
    from ..tournament.boundary.records import EligibleCandidateRecord

    groups = candidate_index(group_rows, "candidate_comparison_group_panel")
    candidates = []
    for row in eligible_rows:
        candidate_id = str(row["candidate_id"])
        candidate = dict(row.get("candidate", {}))
        group = groups[candidate_id]
        factor_values: dict[str, float] = {}
        for greek in row.get("greeks", []):
            for key in ("delta", "gamma", "vega", "theta"):
                if greek.get(key) is not None:
                    factor_values[key] = float(greek[key])
        candidates.append(
            EligibleCandidateRecord(
                candidate_id=candidate_id,
                underlying_id=str(candidate.get("underlying_id", group.get("underlying_id"))),
                horizon=str(row.get("horizon", candidate.get("horizon", group.get("horizon")))),
                objective_family=str(
                    row.get("objective_family", candidate.get("objective_family", group.get("objective_family")))
                ),
                capital_at_risk_bucket=str(group["capital_at_risk_bucket"]),
                lineage_id=str(row.get("lineage_id", candidate.get("lineage_id"))),
                factor_values=factor_values,
            )
        )
    return tuple(candidates)


def _group_records(group_rows: list[dict[str, Any]], eligible_rows: list[dict[str, Any]]):
    from ..tournament.boundary.records import ComparisonGroupRecord

    eligible = candidate_index(eligible_rows, "eligible_strategy_candidate_panel")
    return tuple(
        ComparisonGroupRecord(
            candidate_id=str(row["candidate_id"]),
            comparison_group_id=str(row["comparison_group_id"]),
            underlying_id=str(row["underlying_id"]),
            horizon=str(row["horizon"]),
            objective_family=str(row["objective_family"]),
            capital_at_risk_bucket=str(row["capital_at_risk_bucket"]),
            lineage_id=str(eligible[str(row["candidate_id"])].get("lineage_id")),
        )
        for row in group_rows
    )


def _metric_records(route_rows: list[dict[str, Any]], available_at: datetime, source_artifact_id: str):
    from ..tournament.boundary.records import MetricSourceRecord
    from ..tournament.domain.enums import Direction, MissingnessStatus

    name_map = {"liquidity_score": "liquidity_quality"}
    result = []
    for row in route_rows:
        metric_id = name_map.get(str(row["metric_id"]), str(row["metric_id"]))
        is_available = row.get("status") == "AVAILABLE" and row.get("raw_value") is not None
        status = MissingnessStatus.AVAILABLE if is_available else MissingnessStatus.UNAVAILABLE
        result.append(
            MetricSourceRecord(
                candidate_id=str(row["candidate_id"]),
                metric_id=metric_id,
                raw_value=float(row["raw_value"]) if is_available else None,
                units="currency_loss" if metric_id == "expected_shortfall" else str(row.get("units", "unitless")),
                direction=Direction(str(row["direction"])),
                semantic_version=str(row.get("semantic_version", "2.0.0")),
                source_artifact_id=str(row.get("source_artifact_name", source_artifact_id)),
                available_at=available_at,
                missingness_status=status,
                lineage_id=f"metric:{row['candidate_id']}:{metric_id}",
            )
        )
    return tuple(result)


def _ranking_policy(metric_rows):
    from ..tournament.boundary.records import DominancePolicy, FactorAdjustmentPolicy, MetricPolicy, RankingPolicyRecord
    from ..tournament.domain.enums import FactorMode, MissingAction, MissingnessStatus

    available = [row for row in metric_rows if row.missingness_status == MissingnessStatus.AVAILABLE]
    available_ids = {row.metric_id for row in available}
    preferred = ("expected_net_payoff", "expected_shortfall", "liquidity_quality")
    active = tuple(metric for metric in preferred if metric in available_ids)
    if len(active) < 2:
        active = tuple(sorted(available_ids))
    if not available_ids:
        raise ValueError("no available metrics for tournament policy")
    policies = []
    for metric_id in sorted(available_ids):
        source = next(row for row in available if row.metric_id == metric_id)
        policies.append(
            MetricPolicy(
                metric_id=metric_id,
                canonical_units=source.units,
                direction=source.direction,
                semantic_version=source.semantic_version,
                missing_action=MissingAction.BLOCK,
                active_for_dominance=metric_id in active,
                factor_adjustment_target=metric_id == "expected_net_payoff",
            )
        )
    target = "expected_net_payoff" if "expected_net_payoff" in available_ids else sorted(available_ids)[0]
    return RankingPolicyRecord(
        policy_id="p7-ranking-policy",
        policy_version="2.2.0",
        operational_mode="BASELINE",
        metric_policies=tuple(policies),
        unit_conversions=(),
        factor_adjustment=FactorAdjustmentPolicy(
            mode=FactorMode.BYPASS,
            target_metric_id=target,
            factor_schema_version="option-factors-v1",
            factor_ids=("delta", "gamma", "vega", "theta"),
            static_coefficients={},
            static_intercept=0.0,
            missing_exposure_action="BYPASS_TARGET",
        ),
        dominance=DominancePolicy(
            active_metric_ids=active,
            missing_required_metric_action="INCOMPARABLE",
            exact_max_group_size=5_000,
            exact_max_pair_comparisons=5_000_000,
        ),
        forbidden_field_names=("future_return", "realized_return", "realized_pnl", "outcome", "target_return"),
    )


def _metric_binding(metric_id: str, values: Sequence[float], *, adjusted: bool):
    from ..tournament.boundary.policy_records import MetricBindingPolicy
    from ..tournament.domain.enums import (
        MetricSourcePreference,
        MissingMetricAction,
        NormalizationMethod,
        SmallGroupAction,
        TransformationMethod,
    )

    lower = min(values)
    upper = max(values)
    if lower == upper:
        padding = max(abs(lower) * 0.5, 1.0)
        lower -= padding
        upper += padding
    return MetricBindingPolicy(
        metric_id=metric_id,
        source_preference=(
            MetricSourcePreference.FACTOR_ADJUSTED_PREFERRED
            if adjusted
            else MetricSourcePreference.COMPARABLE_ONLY
        ),
        transformation=TransformationMethod.IDENTITY,
        normalization=NormalizationMethod.ABSOLUTE_RANGE,
        metric_weight=1.0,
        absolute_lower=lower,
        absolute_upper=upper,
        min_group_size=1,
        small_group_action=SmallGroupAction.ABSOLUTE_FALLBACK,
        missing_metric_action=MissingMetricAction.BLOCK_HEAD,
    )


def _scoring_policy(metric_rows, groups):
    from ..tournament.boundary.policy_records import HeadPolicy, ScoringPolicyContextRecord, ScoringPolicyRule
    from ..tournament.domain.enums import MissingHeadAction

    values_by_metric: dict[str, list[float]] = defaultdict(list)
    for row in metric_rows:
        if row.raw_value is not None:
            values_by_metric[row.metric_id].append(float(row.raw_value))
    heads = []
    definitions = (
        ("expected_net_payoff", "ECONOMIC_EDGE", 0.5, True),
        ("expected_shortfall", "DOWNSIDE_SAFETY", 0.3, False),
        ("liquidity_quality", "EXECUTION_QUALITY", 0.2, False),
    )
    for metric_id, head_id, weight, adjusted in definitions:
        if metric_id in values_by_metric:
            heads.append(
                HeadPolicy(
                    head_id=head_id,
                    head_weight=weight,
                    missing_head_action=MissingHeadAction.BLOCK,
                    metric_bindings=(_metric_binding(metric_id, values_by_metric[metric_id], adjusted=adjusted),),
                )
            )
    if not heads:
        raise ValueError("no scoring heads can be constructed")
    total_weight = sum(head.head_weight for head in heads)
    normalized_heads = tuple(head.model_copy(update={"head_weight": head.head_weight / total_weight}) for head in heads)
    pairs = sorted({(group.objective_family, group.horizon) for group in groups})
    rules = tuple(
        ScoringPolicyRule(
            rule_id=f"score-{objective}-{horizon}",
            operational_modes=("BASELINE",),
            objective_families=(objective,),
            horizons=(horizon,),
            max_frontier_layer=10,
            include_incomparable=False,
            heads=normalized_heads,
        )
        for objective, horizon in pairs
    )
    return ScoringPolicyContextRecord(
        policy_id="p7-scoring-policy",
        policy_version="2.2.0",
        operational_mode="BASELINE",
        rules=rules,
        forbidden_field_names=("future_return", "realized_return", "realized_pnl", "outcome", "target_return"),
    )
