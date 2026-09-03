from __future__ import annotations

from collections import defaultdict
from time import perf_counter
from typing import Any, Mapping

from ...s30_models import (
    AgentDisagreementPanel, EvidenceTagPanel, EvidenceTagRecord, ExecutionContext,
    FeatureProjectionConfig, QualityStatus, SocialFeaturePanel, SocialFeatureRecord,
    ValidatedSocietyStatePanel,
)
from .common import (
    S30ContractError, S30TemporalError, _artifact_id, _evidence_summary, _lineage_id,
    _module_result, _parse, _projection_value, _quality_rollup, _round,
    _scan_forbidden, _unique_index, _validate_artifact_alignment,
)

def build_social_features(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Project allowlisted social metrics into the P4 legacy-compatible panel."""

    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    required = {
        "validated_society_state_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
        "feature_projection_config",
    }
    missing = sorted(required - set(inputs))
    if missing:
        raise S30ContractError(f"P3.S30.M01 missing required inputs: {missing}")

    context = _parse(ExecutionContext, context_value, "execution_context")
    society_panel = _parse(
        ValidatedSocietyStatePanel,
        inputs["validated_society_state_panel"],
        "validated_society_state_panel",
    )
    evidence_panel = _parse(EvidenceTagPanel, inputs["evidence_tag_panel"], "evidence_tag_panel")
    disagreement_panel = _parse(
        AgentDisagreementPanel,
        inputs["agent_disagreement_panel"],
        "agent_disagreement_panel",
    )
    projection_config = _parse(
        FeatureProjectionConfig,
        inputs["feature_projection_config"],
        "feature_projection_config",
    )
    _validate_artifact_alignment(context, (society_panel, evidence_panel, disagreement_panel))

    society_by_key = _unique_index(
        society_panel.records,
        lambda item: (item.underlying_id, item.proposition_id, item.horizon, item.as_of_time.date()),
        "society state",
    )
    disagreement_by_key = _unique_index(
        disagreement_panel.records,
        lambda item: item.grain_key,
        "agent disagreement",
    )
    if set(society_by_key) != set(disagreement_by_key):
        raise S30ContractError("grain mismatch between society state and disagreement panel")

    evidence_by_key: dict[tuple[str, str, str, Any], list[EvidenceTagRecord]] = defaultdict(list)
    for record in evidence_panel.records:
        if record.available_at > context.as_of_time:
            raise S30TemporalError(f"evidence {record.evidence_id!r} is after as_of_time")
        evidence_by_key[record.grain_key].append(record)

    records: list[SocialFeatureRecord] = []
    statuses: list[QualityStatus] = []
    reasons: set[str] = set()
    definitions = tuple(
        definition
        for definition in projection_config.definitions
        if definition.source in {"society", "disagreement", "evidence"}
    )
    if not definitions:
        raise S30ContractError("social feature catalog has no social projection definitions")

    for key in sorted(society_by_key, key=lambda item: tuple(str(part) for part in item)):
        society = society_by_key[key]
        disagreement = disagreement_by_key[key]
        evidence_records = evidence_by_key.get(key, [])
        evidence_summary = _evidence_summary(evidence_records)
        status = _quality_rollup((society.quality_status, disagreement.quality_status))
        local_reasons = set(society.quality_reasons + disagreement.quality_reasons)
        statuses.append(status)
        reasons.update(local_reasons)

        for definition in definitions:
            value = _projection_value(definition, society, disagreement, evidence_summary)
            if value is None:
                local_reasons.add(f"FEATURE_VALUE_UNAVAILABLE:{definition.feature_id}")
                reasons.add(f"FEATURE_VALUE_UNAVAILABLE:{definition.feature_id}")
                continue
            rounded = _round(value, projection_config.output_precision)
            record_payload = {
                "grain": key,
                "feature_id": definition.feature_id,
                "value": rounded,
                "catalog": (projection_config.catalog_id, projection_config.catalog_version),
                "input_lineage": (
                    society.lineage_id,
                    disagreement.lineage_id,
                    evidence_panel.lineage_id,
                ),
            }
            records.append(
                SocialFeatureRecord(
                    date=context.as_of_time.date(),
                    as_of_date=context.as_of_time.date(),
                    available_at=context.created_at,
                    underlying=society.underlying_id,
                    proposition_id=society.proposition_id,
                    horizon=society.horizon,
                    social_feature_id=definition.feature_id,
                    feature_name=definition.feature_name,
                    feature_value=rounded,
                    feature_type=definition.feature_type,
                    source_quality_score=min(
                        society.source_quality_score,
                        disagreement.source_quality_score,
                        evidence_summary["mean_source_quality"]
                        if evidence_records
                        else society.source_quality_score,
                    ),
                    evidence_count=len(evidence_records),
                    agent_agreement_score=disagreement.agent_agreement_score,
                    agent_disagreement_score=disagreement.disagreement_score,
                    reference_date=context.as_of_time.date(),
                    formula_id=definition.formula_id,
                    formula_version=definition.formula_version,
                    quality_status=status,
                    quality_reasons=tuple(sorted(local_reasons)),
                    lineage_id=_lineage_id("social-feature-record", record_payload),
                    pipeline_version=context.pipeline_version,
                )
            )

    if not records:
        raise S30ContractError("social feature projection produced no records")
    records.sort(
        key=lambda item: (
            item.underlying,
            item.proposition_id,
            item.horizon,
            item.social_feature_id,
        )
    )
    output_status = _quality_rollup(statuses)
    payload = [record.model_dump(mode="json") for record in records]
    output = SocialFeaturePanel(
        artifact_id=_artifact_id("social-feature-panel", payload),
        created_at=context.created_at,
        lineage_id=_lineage_id(
            "social-feature-panel",
            {
                "society": society_panel.lineage_id,
                "disagreement": disagreement_panel.lineage_id,
                "evidence": evidence_panel.lineage_id,
                "catalog": (
                    projection_config.catalog_id,
                    projection_config.catalog_version,
                ),
                "records": payload,
            },
        ),
        pipeline_version=context.pipeline_version,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        schema_id="p3.s30.social_feature_panel.semantic",
        schema_version="1.0.0",
        quality_status=output_status,
        quality_reasons=tuple(sorted(reasons)),
        records=tuple(records),
    )
    _scan_forbidden(output)
    return _module_result(
        "P3.S30.M01",
        "social_feature_builder",
        "social_feature_panel",
        output,
        started_at,
    )
