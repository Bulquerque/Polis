"""Canonical society-vector assembly for P3.S28.M02."""
from __future__ import annotations

from dataclasses import dataclass

from .artifacts import artifact_kwargs
from .common import require_same_context
from .errors import S28ContractError
from .types import (
    AttentionFeatures,
    AttentionInformationMetrics,
    BeliefDistributionPanel,
    BeliefFeatures,
    CascadeMetricsPanel,
    DynamicsFeatures,
    EmergenceVectorConfig,
    FamilyStatus,
    InformationFeatures,
    MetricLineage,
    MetricStatus,
    S28AggregationSemanticsConfig,
    SocialFeatures,
    SocietyCoverage,
    SocietyFeatures,
    SyntheticSocietyStatePanel,
    SyntheticSocietyStateRecord,
    TagProjectionFeatures,
    TagProjectionPanel,
)

MODULE_ID = "P3.S28.M02"
Group = tuple[str, str, str]

REQUIRED_METRIC_PATHS = (
    "belief.belief_mean", "belief.belief_variance", "belief.belief_entropy", "belief.belief_polarization",
    "belief.bullish_share", "belief.bearish_share", "dynamics.belief_update_velocity_per_day",
    "dynamics.belief_reversal_rate", "attention.attention_intensity", "attention.attention_concentration",
    "social.mean_cascade_size", "social.mean_cascade_depth", "social.social_contagion",
    "social.influence_concentration", "information.information_asymmetry",
    "information.expert_nonexpert_divergence", "information.institutional_disagreement",
    "tag_projection.top_tag_divergence", "tag_projection.top_tag_conditioned_shift",
    "tag_projection.active_tag_projection_count", "tag_projection.suppressed_tag_projection_count",
)


@dataclass(frozen=True, slots=True)
class IndexedInputs:
    belief: dict[Group, object]
    attention: dict[Group, object]
    cascade: dict[Group, object]
    tag_summary: dict[Group, object]


def _key(record: object) -> Group:
    return (record.underlying_id, record.proposition_id, record.horizon)


def _index(records: tuple[object, ...], name: str) -> dict[Group, object]:
    result: dict[Group, object] = {}
    for record in records:
        key = _key(record)
        if key in result:
            raise S28ContractError(f"duplicate grain in {name}: {key}")
        result[key] = record
    return result


def _validate_config(config: EmergenceVectorConfig) -> None:
    if tuple(config.required_metric_paths) != REQUIRED_METRIC_PATHS:
        raise S28ContractError("emergence vector required_metric_paths do not match the canonical S28 surface")
    forbidden = {"future_return", "candidate_score", "rank_score", "portfolio_weight", "trade_decision", "buy_sell_signal"}
    if not forbidden.issubset(set(config.forbidden_direct_targets)):
        raise S28ContractError("emergence vector config is missing forbidden authority fields")


def _family_status(family: str, record: object | None) -> FamilyStatus:
    if record is None:
        return FamilyStatus(family=family, status=MetricStatus.MISSING, reason_codes=("MISSING_UPSTREAM_RECORD",))
    status = record.status
    reasons: tuple[str, ...] = ()
    if status == MetricStatus.NO_COVERAGE:
        reasons = ("UPSTREAM_NO_COVERAGE",)
    elif status == MetricStatus.DEGRADED:
        reasons = ("UPSTREAM_DEGRADED",)
    elif status == MetricStatus.BLOCKED:
        reasons = ("UPSTREAM_BLOCKED",)
    return FamilyStatus(family=family, status=status, reason_codes=reasons)


def _overall_status(statuses: tuple[FamilyStatus, ...]) -> MetricStatus:
    values = {item.status for item in statuses}
    if MetricStatus.BLOCKED in values:
        return MetricStatus.BLOCKED
    if values == {MetricStatus.NO_COVERAGE}:
        return MetricStatus.NO_COVERAGE
    if MetricStatus.MISSING in values or MetricStatus.DEGRADED in values or MetricStatus.NO_COVERAGE in values:
        return MetricStatus.DEGRADED
    return MetricStatus.READY


def _features(belief: object, attention: object | None, cascade: object | None, tag: object | None) -> SocietyFeatures:
    return SocietyFeatures(
        belief=BeliefFeatures(
            belief_mean=belief.belief_mean, belief_variance=belief.belief_variance,
            belief_entropy=belief.belief_entropy, belief_polarization=belief.belief_polarization,
            bullish_share=belief.bullish_share, bearish_share=belief.bearish_share,
        ),
        dynamics=DynamicsFeatures(
            belief_update_velocity_per_day=belief.belief_update_velocity_per_day,
            belief_reversal_rate=belief.belief_reversal_rate,
            applicability=belief.dynamics_applicability,
        ),
        attention=AttentionFeatures(
            attention_intensity=attention.attention_intensity if attention else None,
            attention_concentration=attention.attention_concentration if attention else None,
        ),
        social=SocialFeatures(
            mean_cascade_size=cascade.mean_cascade_size if cascade else None,
            mean_cascade_depth=cascade.mean_cascade_depth if cascade else None,
            social_contagion=cascade.social_contagion if cascade else None,
            influence_concentration=cascade.influence_concentration if cascade else None,
        ),
        information=InformationFeatures(
            information_asymmetry=attention.information_asymmetry if attention else None,
            expert_nonexpert_divergence=tag.expert_nonexpert_divergence if tag else None,
            institutional_disagreement=tag.institutional_disagreement if tag else None,
            expert_nonexpert_applicability=tag.expert_nonexpert_applicability if tag else "NOT_APPLICABLE_INSUFFICIENT_COHORTS",
            institutional_applicability=tag.institutional_applicability if tag else "NOT_APPLICABLE_INSUFFICIENT_COHORTS",
        ),
        tag_projection=TagProjectionFeatures(
            top_tag_divergence=tag.top_tag_divergence if tag else None,
            top_tag_conditioned_shift=tag.top_tag_conditioned_shift if tag else None,
            active_tag_projection_count=tag.active_tag_projection_count if tag else 0,
            suppressed_tag_projection_count=tag.suppressed_tag_projection_count if tag else 0,
        ),
    )


def _coverage(belief: object, attention: object | None, cascade: object | None, tag: object | None) -> SocietyCoverage:
    return SocietyCoverage(
        active_person_count=belief.active_person_count,
        population_coverage_ratio=belief.population_coverage_ratio,
        belief_coverage_ratio=belief.weight_coverage_ratio,
        attention_population_coverage_ratio=attention.population_coverage_ratio if attention else None,
        effective_n=belief.effective_n,
        causal_coverage_ratio=cascade.causal_coverage_ratio if cascade else None,
        tag_projection_count=tag.active_tag_projection_count if tag else 0,
    )


def _metric_lineage(belief: object, attention: object | None, cascade: object | None, tag: object | None) -> tuple[MetricLineage, ...]:
    families = [
        ("belief", "belief_distribution_panel", belief),
        ("dynamics", "belief_distribution_panel", belief),
        ("attention", "attention_information_metrics", attention),
        ("social", "cascade_metrics_panel", cascade),
        ("information.information_asymmetry", "attention_information_metrics", attention),
        ("information.tag_conditioned", "tag_projection_panel", tag),
        ("tag_projection", "tag_projection_panel", tag),
    ]
    return tuple(
        MetricLineage(metric_path=path, source_artifact=source, input_lineage_ids=item.input_lineage_ids)
        for path, source, item in families if item is not None
    )


def _record(key: Group, belief: object, indexed: IndexedInputs, config: EmergenceVectorConfig) -> SyntheticSocietyStateRecord:
    attention = indexed.attention.get(key)
    cascade = indexed.cascade.get(key)
    tag = indexed.tag_summary.get(key)
    for item in (belief, attention, cascade, tag):
        if item is not None and item.as_of_time != belief.as_of_time:
            raise S28ContractError(f"as_of mismatch within vector grain: {key}")
    statuses = (
        _family_status("belief", belief), _family_status("attention", attention),
        _family_status("social", cascade), _family_status("tag_projection", tag),
    )
    lineages = sorted({lineage for item in (belief, attention, cascade, tag) if item is not None for lineage in item.input_lineage_ids})
    return SyntheticSocietyStateRecord(
        underlying_id=key[0], proposition_id=key[1], horizon=key[2], as_of_time=belief.as_of_time,
        vector_version=config.vector_version,
        formula_versions={
            "belief": belief.formula_version,
            "attention": attention.formula_version if attention else "MISSING",
            "cascade": cascade.formula_version if cascade else "MISSING",
            "tag_projection": tag.formula_version if tag else "MISSING",
        },
        status=_overall_status(statuses), features=_features(belief, attention, cascade, tag),
        coverage=_coverage(belief, attention, cascade, tag), family_statuses=statuses,
        metric_lineage=_metric_lineage(belief, attention, cascade, tag), input_lineage_ids=tuple(lineages),
    )


def build_society_vector(
    *,
    belief_distribution_panel: BeliefDistributionPanel,
    attention_information_metrics: AttentionInformationMetrics,
    cascade_metrics_panel: CascadeMetricsPanel,
    tag_projection_panel: TagProjectionPanel,
    emergence_vector_config: EmergenceVectorConfig,
    aggregation_semantics_config: S28AggregationSemanticsConfig,
) -> SyntheticSocietyStatePanel:
    run_id, cycle_id, as_of = require_same_context(
        belief_distribution_panel, attention_information_metrics, cascade_metrics_panel, tag_projection_panel
    )
    _validate_config(emergence_vector_config)
    if tag_projection_panel.formula_version != aggregation_semantics_config.formula_version:
        raise S28ContractError("tag projection formula version conflicts with aggregation config")
    indexed = IndexedInputs(
        belief=_index(belief_distribution_panel.records, "belief_distribution_panel"),
        attention=_index(attention_information_metrics.records, "attention_information_metrics"),
        cascade=_index(cascade_metrics_panel.records, "cascade_metrics_panel"),
        tag_summary=_index(tag_projection_panel.summaries, "tag_projection_panel.summaries"),
    )
    records = tuple(_record(key, indexed.belief[key], indexed, emergence_vector_config) for key in sorted(indexed.belief))
    lineages = (
        belief_distribution_panel.lineage_id, attention_information_metrics.lineage_id,
        cascade_metrics_panel.lineage_id, tag_projection_panel.lineage_id,
    )
    kwargs = artifact_kwargs(
        module_id=MODULE_ID, output_name="synthetic_society_state_panel", schema_version="p3.s28.v1",
        run_id=run_id, cycle_id=cycle_id, as_of_time=as_of, lineages=lineages,
    )
    return SyntheticSocietyStatePanel(
        **kwargs, vector_id=emergence_vector_config.vector_id,
        vector_version=emergence_vector_config.vector_version, records=records,
    )
