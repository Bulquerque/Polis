from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.artifacts import build_artifact
from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.records import (
    ArtifactReference,
    ComparisonGroupRecord,
    DominancePolicy,
    EligibleCandidateRecord,
    FactorAdjustmentPolicy,
    FoundationAuditRecord,
    HandoffManifestRecord,
    MetricPolicy,
    MetricSourceRecord,
    OptionFactorModelRecord,
    RankingPolicyRecord,
    UnitConversionPolicy,
)
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.enums import (
    Direction,
    FactorMode,
    MissingAction,
    MissingnessStatus,
    ModelQualificationStatus,
)

DECISION_TIME = datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)
RUN_ID = "run-fixture-001"
CYCLE_ID = "cycle-fixture-001"


def _artifact(name: str, records: tuple[Any, ...], module: str = "P7.S2.M04") -> dict[str, Any]:
    artifact = build_artifact(
        artifact_name=name,
        schema_version="1.0.0",
        producer_module_id=module,
        run_id=RUN_ID,
        cycle_id=CYCLE_ID,
        decision_time=DECISION_TIME,
        execution_time=DECISION_TIME,
        lineage_id=f"lineage:{name}",
        records=records,
    )
    return artifact.model_dump(mode="json")


def metric_policies() -> tuple[MetricPolicy, ...]:
    return (
        MetricPolicy(
            metric_id="expected_net_payoff",
            canonical_units="currency",
            direction=Direction.MAXIMIZE,
            semantic_version="1.0.0",
            missing_action=MissingAction.BLOCK,
            active_for_dominance=True,
            factor_adjustment_target=True,
        ),
        MetricPolicy(
            metric_id="expected_shortfall",
            canonical_units="currency_loss",
            direction=Direction.MINIMIZE,
            semantic_version="1.0.0",
            missing_action=MissingAction.BLOCK,
            active_for_dominance=True,
        ),
        MetricPolicy(
            metric_id="liquidity_quality",
            canonical_units="normalized_score",
            direction=Direction.MAXIMIZE,
            semantic_version="1.0.0",
            missing_action=MissingAction.BLOCK,
            active_for_dominance=True,
            epsilon_absolute=1e-12,
        ),
    )


def ranking_policy(
    *,
    factor_mode: FactorMode = FactorMode.BYPASS,
    static_coefficients: dict[str, float] | None = None,
    missing_action: str = "UNAVAILABLE",
    max_group_size: int = 1000,
    max_pairs: int = 1_000_000,
    unit_conversions: tuple[UnitConversionPolicy, ...] = (),
) -> RankingPolicyRecord:
    return RankingPolicyRecord(
        policy_id="p7-s3-policy-v1",
        policy_version="1.0.0",
        operational_mode="BASELINE",
        metric_policies=metric_policies(),
        unit_conversions=unit_conversions,
        factor_adjustment=FactorAdjustmentPolicy(
            mode=factor_mode,
            target_metric_id="expected_net_payoff",
            factor_schema_version="option-factors-v1",
            factor_ids=("delta", "vega"),
            static_coefficients=static_coefficients or {},
            static_intercept=0.0,
            missing_exposure_action=missing_action,
        ),
        dominance=DominancePolicy(
            active_metric_ids=("expected_net_payoff", "expected_shortfall", "liquidity_quality"),
            missing_required_metric_action="INCOMPARABLE",
            exact_max_group_size=max_group_size,
            exact_max_pair_comparisons=max_pairs,
        ),
        forbidden_field_names=(
            "future_return",
            "realized_return",
            "realized_pnl",
            "outcome",
            "target_return",
        ),
    )


def make_bundle(
    *,
    factor_mode: FactorMode = FactorMode.BYPASS,
    include_factor_model: bool = False,
    factor_training_cutoff: datetime | None = None,
    static_coefficients: dict[str, float] | None = None,
    separate_groups: bool = False,
    missing_metric: tuple[str, str] | None = None,
    unit_override: tuple[str, str, str] | None = None,
    unit_conversions: tuple[UnitConversionPolicy, ...] = (),
    max_group_size: int = 1000,
    max_pairs: int = 1_000_000,
    value_overrides: dict[tuple[str, str], float] | None = None,
    reverse_records: bool = False,
) -> dict[str, Any]:
    candidates = (
        EligibleCandidateRecord(
            candidate_id="A",
            underlying_id="XYZ",
            horizon="5D",
            objective_family="RANGE",
            capital_at_risk_bucket="SMALL",
            lineage_id="candidate:A",
            factor_values={"delta": 0.10, "vega": 0.20},
        ),
        EligibleCandidateRecord(
            candidate_id="B",
            underlying_id="XYZ",
            horizon="5D",
            objective_family="RANGE",
            capital_at_risk_bucket="SMALL",
            lineage_id="candidate:B",
            factor_values={"delta": 0.20, "vega": 0.10},
        ),
        EligibleCandidateRecord(
            candidate_id="C",
            underlying_id="XYZ",
            horizon="5D",
            objective_family="RANGE",
            capital_at_risk_bucket="SMALL",
            lineage_id="candidate:C",
            factor_values={"delta": 0.30, "vega": 0.30},
        ),
    )
    groups = tuple(
        ComparisonGroupRecord(
            candidate_id=row.candidate_id,
            comparison_group_id=("group-2" if separate_groups and row.candidate_id == "B" else "group-1"),
            underlying_id=row.underlying_id,
            horizon=row.horizon,
            objective_family=row.objective_family,
            capital_at_risk_bucket=row.capital_at_risk_bucket,
            lineage_id=row.lineage_id,
        )
        for row in candidates
    )
    values = {
        "A": {"expected_net_payoff": 12.0, "expected_shortfall": 5.0, "liquidity_quality": 0.8},
        "B": {"expected_net_payoff": 10.0, "expected_shortfall": 6.0, "liquidity_quality": 0.7},
        "C": {"expected_net_payoff": 15.0, "expected_shortfall": 9.0, "liquidity_quality": 0.9},
    }
    for (candidate_key, metric_key), override_value in (value_overrides or {}).items():
        values[candidate_key][metric_key] = override_value
    units = {
        "expected_net_payoff": "currency",
        "expected_shortfall": "currency_loss",
        "liquidity_quality": "normalized_score",
    }
    directions = {
        "expected_net_payoff": Direction.MAXIMIZE,
        "expected_shortfall": Direction.MINIMIZE,
        "liquidity_quality": Direction.MAXIMIZE,
    }
    if unit_override:
        candidate_id, metric_id, override_units = unit_override
    else:
        candidate_id = metric_id = override_units = ""
    metrics: list[MetricSourceRecord] = []
    for candidate in candidates:
        for current_metric, value in values[candidate.candidate_id].items():
            if missing_metric == (candidate.candidate_id, current_metric):
                continue
            current_units = override_units if (candidate.candidate_id, current_metric) == (candidate_id, metric_id) else units[current_metric]
            metrics.append(
                MetricSourceRecord(
                    candidate_id=candidate.candidate_id,
                    metric_id=current_metric,
                    raw_value=value,
                    units=current_units,
                    direction=directions[current_metric],
                    semantic_version="1.0.0",
                    source_artifact_id="p6:strategy-risk-panel",
                    available_at=DECISION_TIME,
                    missingness_status=MissingnessStatus.AVAILABLE,
                    lineage_id=f"metric:{candidate.candidate_id}:{current_metric}",
                )
            )
    policy = ranking_policy(
        factor_mode=factor_mode,
        static_coefficients=static_coefficients,
        unit_conversions=unit_conversions,
        max_group_size=max_group_size,
        max_pairs=max_pairs,
    )
    candidate_records = tuple(reversed(candidates)) if reverse_records else candidates
    group_records = tuple(reversed(groups)) if reverse_records else groups
    metric_records = tuple(reversed(metrics)) if reverse_records else tuple(metrics)
    artifacts = {
        "eligible_strategy_candidate_panel": _artifact("eligible_strategy_candidate_panel", candidate_records),
        "candidate_comparison_group_panel": _artifact("candidate_comparison_group_panel", group_records),
        "candidate_metric_source_panel": _artifact("candidate_metric_source_panel", metric_records),
        "ranking_policy_context": _artifact("ranking_policy_context", (policy,)),
        "runtime_foundation_audit_report": _artifact(
            "runtime_foundation_audit_report",
            (
                FoundationAuditRecord(
                    status="PASS",
                    candidate_count=len(candidates),
                    comparison_group_count=len({row.comparison_group_id for row in groups}),
                    comparison_groups_frozen=True,
                    candidate_reconciliation_passed=True,
                    forbidden_field_scan_passed=True,
                ),
            ),
        ),
    }
    refs = tuple(
        ArtifactReference(
            artifact_name=name,
            artifact_id=artifact["artifact_id"],
            content_sha256=artifact["content_sha256"],
            schema_version=artifact["schema_version"],
            record_count=artifact["record_count"],
        )
        for name, artifact in sorted(artifacts.items())
    )
    artifacts["runtime_foundation_handoff_manifest"] = _artifact(
        "runtime_foundation_handoff_manifest",
        (
            HandoffManifestRecord(
                contract_id="runtime_foundation_handoff_v1",
                producer="FOUNDATION",
                consumer="TOURNAMENT",
                references=refs,
            ),
        ),
        module="P7.S2.M04",
    )
    if include_factor_model:
        model = OptionFactorModelRecord(
            model_id="factor-model-v1",
            model_version="1.0.0",
            qualification_status=ModelQualificationStatus.QUALIFIED,
            training_cutoff_at=factor_training_cutoff or DECISION_TIME,
            factor_schema_version="option-factors-v1",
            target_metric_id="expected_net_payoff",
            intercept=0.0,
            coefficients={"delta": 2.0, "vega": 1.0},
            lineage_id="factor-model-lineage",
        )
        artifacts["option_factor_model_artifact"] = _artifact(
            "option_factor_model_artifact", (model,), module="P7.OFFLINE.FACTOR"
        )
    return deepcopy(artifacts)


def execution_config() -> dict[str, Any]:
    return {
        "execution_time": DECISION_TIME.isoformat(),
        "strict_hash_validation": True,
        "emit_debug_events": True,
        "numerical_tolerance": 1e-10,
    }
