"""Quality guard for P3.S28.M03."""
from __future__ import annotations

from math import sqrt

from .artifacts import artifact_kwargs
from .common import require_not_future, require_same_context
from .errors import S28ContractError
from .statistics import clamp
from .types import (
    EmergenceVectorConfig,
    IssueSeverity,
    MetricStatus,
    Phase3RunSnapshot,
    QualityAssessment,
    QualityIssue,
    QualityStatus,
    SourceQualityPanel,
    SyntheticSocietyStatePanel,
    ValidatedSocietyStatePanel,
    ValidatedSocietyStateRecord,
)

MODULE_ID = "P3.S28.M03"


def _flatten_features(record: object) -> dict[str, float | int | None]:
    features = record.features
    return {
        "belief.belief_mean": features.belief.belief_mean,
        "belief.belief_variance": features.belief.belief_variance,
        "belief.belief_entropy": features.belief.belief_entropy,
        "belief.belief_polarization": features.belief.belief_polarization,
        "belief.bullish_share": features.belief.bullish_share,
        "belief.bearish_share": features.belief.bearish_share,
        "dynamics.belief_update_velocity_per_day": features.dynamics.belief_update_velocity_per_day,
        "dynamics.belief_reversal_rate": features.dynamics.belief_reversal_rate,
        "attention.attention_intensity": features.attention.attention_intensity,
        "attention.attention_concentration": features.attention.attention_concentration,
        "social.mean_cascade_size": features.social.mean_cascade_size,
        "social.mean_cascade_depth": features.social.mean_cascade_depth,
        "social.social_contagion": features.social.social_contagion,
        "social.influence_concentration": features.social.influence_concentration,
        "information.information_asymmetry": features.information.information_asymmetry,
        "information.expert_nonexpert_divergence": features.information.expert_nonexpert_divergence,
        "information.institutional_disagreement": features.information.institutional_disagreement,
        "tag_projection.top_tag_divergence": features.tag_projection.top_tag_divergence,
        "tag_projection.top_tag_conditioned_shift": features.tag_projection.top_tag_conditioned_shift,
        "tag_projection.active_tag_projection_count": features.tag_projection.active_tag_projection_count,
        "tag_projection.suppressed_tag_projection_count": features.tag_projection.suppressed_tag_projection_count,
    }


def _source_scores(panel: SourceQualityPanel, config: EmergenceVectorConfig) -> tuple[dict[str, float], list[QualityIssue]]:
    records = {record.artifact_id: record for record in panel.records}
    scores: dict[str, float] = {}
    issues: list[QualityIssue] = []
    for artifact_id in config.required_source_artifacts:
        record = records.get(artifact_id)
        if record is None:
            issues.append(QualityIssue(
                code="SOURCE_QUALITY_MISSING", severity=IssueSeverity.ERROR, dimension="source_quality",
                observed=artifact_id, threshold="required", message=f"source quality is missing for {artifact_id}",
            ))
            continue
        scores[artifact_id] = min(
            record.quality_score, record.completeness, record.validity,
            record.timeliness, record.lineage_completeness,
        )
    return scores, issues


def _uncertainty(record: object) -> float | None:
    components: list[float] = []
    variance = record.features.belief.belief_variance
    asymmetry = record.features.information.information_asymmetry
    if variance is not None:
        components.append(clamp(sqrt(variance)))
    if asymmetry is not None:
        components.append(clamp(asymmetry))
    components.append(1.0 - record.coverage.belief_coverage_ratio)
    if record.coverage.causal_coverage_ratio is not None:
        components.append(1.0 - record.coverage.causal_coverage_ratio)
    return max(components) if components else None


def _threshold_issue(code: str, dimension: str, observed: float | int, pass_threshold: float | int, degraded_threshold: float | int, higher_is_better: bool = True) -> QualityIssue | None:
    if higher_is_better:
        if observed < degraded_threshold:
            return QualityIssue(code=code + "_BLOCK", severity=IssueSeverity.ERROR, dimension=dimension, observed=observed, threshold=degraded_threshold, message=f"{dimension} is below blocking threshold")
        if observed < pass_threshold:
            return QualityIssue(code=code + "_DEGRADE", severity=IssueSeverity.WARNING, dimension=dimension, observed=observed, threshold=pass_threshold, message=f"{dimension} is below pass threshold")
    else:
        if observed > degraded_threshold:
            return QualityIssue(code=code + "_BLOCK", severity=IssueSeverity.ERROR, dimension=dimension, observed=observed, threshold=degraded_threshold, message=f"{dimension} exceeds blocking threshold")
        if observed > pass_threshold:
            return QualityIssue(code=code + "_DEGRADE", severity=IssueSeverity.WARNING, dimension=dimension, observed=observed, threshold=pass_threshold, message=f"{dimension} exceeds pass threshold")
    return None


def _dimension_issues(record: object, completeness: float, source_quality: float | None, uncertainty: float | None, config: EmergenceVectorConfig) -> list[QualityIssue]:
    thresholds = config.thresholds
    checks = [
        _threshold_issue("ACTIVE_PERSON_COUNT", "active_person_count", record.coverage.active_person_count, thresholds.min_active_person_count_pass, thresholds.min_active_person_count_degraded),
        _threshold_issue("EFFECTIVE_N", "effective_n", record.coverage.effective_n, thresholds.min_effective_n_pass, thresholds.min_effective_n_degraded),
        _threshold_issue("POPULATION_COVERAGE", "population_coverage", record.coverage.population_coverage_ratio, thresholds.min_population_coverage_pass, thresholds.min_population_coverage_degraded),
        _threshold_issue("BELIEF_COVERAGE", "belief_coverage", record.coverage.belief_coverage_ratio, thresholds.min_belief_coverage_pass, thresholds.min_belief_coverage_degraded),
        _threshold_issue("METRIC_COMPLETENESS", "metric_completeness", completeness, thresholds.min_metric_completeness_pass, thresholds.min_metric_completeness_degraded),
    ]
    if record.coverage.causal_coverage_ratio is not None:
        checks.append(_threshold_issue("CAUSAL_COVERAGE", "causal_coverage", record.coverage.causal_coverage_ratio, thresholds.min_causal_coverage_pass, thresholds.min_causal_coverage_degraded))
    if source_quality is not None:
        checks.append(_threshold_issue("SOURCE_QUALITY", "source_quality", source_quality, thresholds.min_source_quality_pass, thresholds.min_source_quality_degraded))
    if uncertainty is not None:
        checks.append(_threshold_issue("UNCERTAINTY", "uncertainty", uncertainty, thresholds.max_uncertainty_pass, thresholds.max_uncertainty_degraded, higher_is_better=False))
    return [issue for issue in checks if issue is not None]


def _status(record: object, issues: list[QualityIssue]) -> QualityStatus:
    if record.status == MetricStatus.NO_COVERAGE:
        return QualityStatus.NO_COVERAGE
    if record.status == MetricStatus.BLOCKED or any(issue.severity == IssueSeverity.ERROR for issue in issues):
        return QualityStatus.BLOCKED
    if record.status != MetricStatus.READY or issues:
        return QualityStatus.DEGRADED
    return QualityStatus.PASS


def _assessment(record: object, source_scores: dict[str, float], base_issues: list[QualityIssue], config: EmergenceVectorConfig) -> QualityAssessment:
    values = _flatten_features(record)
    required = tuple(config.required_metric_paths)
    if record.features.dynamics.applicability == "NOT_APPLICABLE_GENESIS":
        required = tuple(path for path in required if not path.startswith("dynamics."))
    if record.features.information.expert_nonexpert_applicability == "NOT_APPLICABLE_INSUFFICIENT_COHORTS":
        required = tuple(path for path in required if path != "information.expert_nonexpert_divergence")
    if record.features.information.institutional_applicability == "NOT_APPLICABLE_INSUFFICIENT_COHORTS":
        required = tuple(path for path in required if path != "information.institutional_disagreement")
    completeness = sum(values[path] is not None for path in required) / len(required)
    source_quality = min(source_scores.values()) if source_scores else None
    uncertainty = _uncertainty(record)
    issues = [*base_issues, *_dimension_issues(record, completeness, source_quality, uncertainty, config)]
    coverage_score = min(record.coverage.population_coverage_ratio, record.coverage.belief_coverage_ratio, clamp(record.coverage.effective_n / config.thresholds.min_effective_n_pass))
    if record.coverage.causal_coverage_ratio is not None:
        coverage_score = min(coverage_score, record.coverage.causal_coverage_ratio)
    quality_score = None
    if source_quality is not None and uncertainty is not None:
        weights = config.quality_weights
        quality_score = clamp(
            weights.completeness * completeness + weights.source_quality * source_quality
            + weights.coverage * coverage_score + weights.uncertainty_complement * (1.0 - uncertainty)
        )
    return QualityAssessment(
        status=_status(record, issues), quality_score=quality_score, metric_completeness=completeness,
        source_quality_score=source_quality, coverage_score=coverage_score, uncertainty_score=uncertainty,
        issues=tuple(issues), source_artifact_scores=source_scores,
    )


def validate_society_vector(
    *,
    synthetic_society_state_panel: SyntheticSocietyStatePanel,
    source_quality_panel: SourceQualityPanel,
    phase3_run_snapshot: Phase3RunSnapshot,
    emergence_vector_config: EmergenceVectorConfig,
) -> ValidatedSocietyStatePanel:
    run_id, cycle_id, as_of = require_same_context(synthetic_society_state_panel, source_quality_panel, phase3_run_snapshot)
    for item in source_quality_panel.records:
        require_not_future(item.assessed_at, as_of=as_of, label="source_quality.assessed_at")
    if synthetic_society_state_panel.vector_id != emergence_vector_config.vector_id:
        raise S28ContractError("vector_id conflicts with emergence vector config")
    if synthetic_society_state_panel.vector_version != emergence_vector_config.vector_version:
        raise S28ContractError("vector_version conflicts with emergence vector config")
    source_scores, base_issues = _source_scores(source_quality_panel, emergence_vector_config)
    records = tuple(
        ValidatedSocietyStateRecord(
            underlying_id=item.underlying_id, proposition_id=item.proposition_id, horizon=item.horizon,
            as_of_time=item.as_of_time, vector_version=item.vector_version,
            formula_versions=item.formula_versions, features=item.features, coverage=item.coverage,
            family_statuses=item.family_statuses, metric_lineage=item.metric_lineage,
            quality=_assessment(item, source_scores, base_issues, emergence_vector_config),
            input_lineage_ids=item.input_lineage_ids,
        )
        for item in synthetic_society_state_panel.records
    )
    lineages = (synthetic_society_state_panel.lineage_id, source_quality_panel.lineage_id, phase3_run_snapshot.lineage_id)
    kwargs = artifact_kwargs(
        module_id=MODULE_ID, output_name="validated_society_state_panel", schema_version="p3.s28.v1",
        run_id=run_id, cycle_id=cycle_id, as_of_time=as_of, lineages=lineages,
    )
    return ValidatedSocietyStatePanel(
        **kwargs, vector_id=synthetic_society_state_panel.vector_id,
        vector_version=synthetic_society_state_panel.vector_version,
        snapshot_id=phase3_run_snapshot.snapshot_id, records=records,
    )
