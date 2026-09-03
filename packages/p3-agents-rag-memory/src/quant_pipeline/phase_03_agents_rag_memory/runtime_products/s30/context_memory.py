from __future__ import annotations

from collections import defaultdict
from math import fsum
from time import perf_counter
from typing import Any, Mapping, Sequence

from ...s30_models import (
    ContextMemoryFeaturePanel, ContextMemoryFeatureRecord, EvidenceTagPanel,
    EvidenceTagRecord, ExecutionContext, FeatureProjectionConfig, MemoryRecord,
    NextMemoryState, PrivacyClass, QualityStatus, ValidatedSocietyStatePanel,
)
from .common import (
    S30ContractError, S30TemporalError, _artifact_id, _evidence_summary, _lineage_id,
    _module_result, _parse, _quality_rollup, _round, _scan_forbidden,
    _validate_artifact_alignment,
)

def _memory_summary(
    records: Sequence[MemoryRecord],
    population_size: int,
) -> dict[str, float]:
    if not records:
        return {
            "item_count": 0.0,
            "mean_confidence": 0.0,
            "mean_importance": 0.0,
            "mean_retrievability": 0.0,
            "mean_source_quality": 0.0,
            "evidence_link_count": 0.0,
            "population_coverage_ratio": 0.0,
        }
    count = len(records)
    person_count = len({record.person_id for record in records})
    return {
        "item_count": float(count),
        "mean_confidence": fsum(record.confidence for record in records) / count,
        "mean_importance": fsum(record.importance for record in records) / count,
        "mean_retrievability": fsum(record.retrievability for record in records) / count,
        "mean_source_quality": fsum(record.source_quality_score for record in records) / count,
        "evidence_link_count": float(sum(len(record.evidence_refs) for record in records)),
        "population_coverage_ratio": person_count / population_size if population_size else 0.0,
    }


def build_context_memory_features(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Project private-safe memory and context aggregates for P4."""

    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    required = {
        "next_memory_state",
        "validated_society_state_panel",
        "evidence_tag_panel",
        "feature_projection_config",
    }
    missing = sorted(required - set(inputs))
    if missing:
        raise S30ContractError(f"P3.S30.M02 missing required inputs: {missing}")

    context = _parse(ExecutionContext, context_value, "execution_context")
    memory_state = _parse(NextMemoryState, inputs["next_memory_state"], "next_memory_state")
    society_panel = _parse(
        ValidatedSocietyStatePanel,
        inputs["validated_society_state_panel"],
        "validated_society_state_panel",
    )
    evidence_panel = _parse(EvidenceTagPanel, inputs["evidence_tag_panel"], "evidence_tag_panel")
    projection_config = _parse(
        FeatureProjectionConfig,
        inputs["feature_projection_config"],
        "feature_projection_config",
    )
    _validate_artifact_alignment(context, (memory_state, society_panel, evidence_panel))

    memory_by_key: dict[tuple[str, str, str], list[MemoryRecord]] = defaultdict(list)
    for record in memory_state.records:
        if record.available_at > context.as_of_time:
            raise S30TemporalError(f"memory {record.memory_id!r} is after as_of_time")
        memory_by_key[record.grain_key].append(record)
    evidence_by_key: dict[tuple[str, str, str, Any], list[EvidenceTagRecord]] = defaultdict(list)
    for record in evidence_panel.records:
        if record.available_at > context.as_of_time:
            raise S30TemporalError(f"evidence {record.evidence_id!r} is after as_of_time")
        evidence_by_key[record.grain_key].append(record)

    definitions = tuple(
        item
        for item in projection_config.definitions
        if item.source in {"memory", "evidence"}
    )
    if not definitions:
        raise S30ContractError("projection catalog has no context/memory definitions")

    records: list[ContextMemoryFeatureRecord] = []
    statuses: list[QualityStatus] = []
    reasons: set[str] = set()
    for society in sorted(
        society_panel.records,
        key=lambda item: (
            item.underlying_id,
            item.proposition_id,
            item.horizon,
            item.as_of_time,
        ),
    ):
        key3 = society.underlying_id, society.proposition_id, society.horizon
        key4 = key3 + (society.as_of_time.date(),)
        memory_records = memory_by_key.get(key3, [])
        evidence_records = evidence_by_key.get(key4, [])
        memory_summary = _memory_summary(memory_records, memory_state.population_size)
        evidence_summary = _evidence_summary(evidence_records)
        coverage = memory_summary["population_coverage_ratio"]
        status = society.quality_status
        local_reasons = set(society.quality_reasons)
        if coverage < projection_config.min_memory_population_coverage:
            if status != QualityStatus.BLOCKED:
                status = QualityStatus.DEGRADED
            local_reasons.add("MEMORY_POPULATION_COVERAGE_BELOW_PREFERRED_MINIMUM")
        statuses.append(status)
        reasons.update(local_reasons)

        for definition in definitions:
            summary = memory_summary if definition.source == "memory" else evidence_summary
            if definition.source_field not in summary:
                raise S30ContractError(
                    f"unknown {definition.source} summary field {definition.source_field!r}"
                )
            value = _round(summary[definition.source_field], projection_config.output_precision)
            source_quality = (
                memory_summary["mean_source_quality"]
                if definition.source == "memory" and memory_records
                else evidence_summary["mean_source_quality"]
                if definition.source == "evidence" and evidence_records
                else society.source_quality_score
            )
            record_payload = {
                "grain": key3,
                "feature_id": definition.feature_id,
                "value": value,
                "input_lineage": (
                    memory_state.lineage_id,
                    society.lineage_id,
                    evidence_panel.lineage_id,
                ),
            }
            records.append(
                ContextMemoryFeatureRecord(
                    date=context.as_of_time.date(),
                    as_of_date=context.as_of_time.date(),
                    available_at=context.created_at,
                    underlying=society.underlying_id,
                    proposition_id=society.proposition_id,
                    horizon=society.horizon,
                    context_memory_feature_id=definition.feature_id,
                    feature_name=definition.feature_name,
                    feature_value=value,
                    feature_type=definition.feature_type,
                    source_quality_score=source_quality,
                    evidence_count=len(evidence_records),
                    population_coverage_ratio=coverage,
                    uncertainty_score=_round(1.0 - source_quality, projection_config.output_precision),
                    privacy_class=PrivacyClass.INTERNAL_AGGREGATE,
                    formula_id=definition.formula_id,
                    formula_version=definition.formula_version,
                    quality_status=status,
                    quality_reasons=tuple(sorted(local_reasons)),
                    lineage_id=_lineage_id("context-memory-feature-record", record_payload),
                    pipeline_version=context.pipeline_version,
                )
            )

    if not records:
        raise S30ContractError("context/memory feature projection produced no records")
    records.sort(
        key=lambda item: (
            item.underlying,
            item.proposition_id,
            item.horizon,
            item.context_memory_feature_id,
        )
    )
    payload = [record.model_dump(mode="json") for record in records]
    output = ContextMemoryFeaturePanel(
        artifact_id=_artifact_id("context-memory-feature-panel", payload),
        created_at=context.created_at,
        lineage_id=_lineage_id(
            "context-memory-feature-panel",
            {
                "memory": memory_state.lineage_id,
                "society": society_panel.lineage_id,
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
        schema_id="p3.s30.context_memory_feature_panel.semantic",
        schema_version="1.0.0",
        quality_status=_quality_rollup(statuses),
        quality_reasons=tuple(sorted(reasons)),
        records=tuple(records),
    )
    _scan_forbidden(output)
    return _module_result(
        "P3.S30.M02",
        "context_memory_feature_builder",
        "context_memory_feature_panel",
        output,
        started_at,
    )
