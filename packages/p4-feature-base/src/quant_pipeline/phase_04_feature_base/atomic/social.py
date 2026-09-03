from __future__ import annotations

from collections import defaultdict
import math
import re

from ..feature_records import one_record
from ..economic_models import AtomicFeatureRecord, CanonicalObservation, ObserverSpec, QualityState
from ..provenance import combine_quality, from_observations, is_usable

MODULE_ID = "P4.S4.M07"
SUPPORTED_OBSERVERS = {
    "social.feature_passthrough",
    "social.evidence_count",
    "social.evidence_balance",
    "social.evidence_quality_weighted_balance",
    "social.disagreement_state",
    "social.hypothesis_count",
    "social.narrative_shift",
}


def _safe(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")


def _copy_spec(spec: ObserverSpec, suffix: str) -> ObserverSpec:
    return spec.model_copy(update={"feature_id": f"{spec.feature_id}.{_safe(suffix)}"})


def _passthrough(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    output: list[AtomicFeatureRecord] = []
    for row in observations:
        if not is_usable(row) or not row.variable_id.startswith(("social.feature.", "agent.disagreement.", "memory.feature.")):
            continue
        if not isinstance(row.value, (int, float)) or isinstance(row.value, bool):
            continue
        dynamic = _copy_spec(spec, row.variable_id)
        output.append(
            one_record(
                decision_time=row.decision_time,
                entity_id=row.entity_id,
                spec=dynamic,
                value=float(row.value),
                unit=row.unit or "score",
                available_at=row.available_at,
                lineage_ids=[row.record_lineage_id],
                modalities=[row.source_modality],
                quality_state=row.quality_state,
                attributes={"source_variable_id": row.variable_id, **row.attributes},
            )
        )
    return output


def _source_quality(row: CanonicalObservation) -> float | None:
    raw = row.attributes.get("source_quality_score")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0.0 <= value <= 1.0 else None


def _evidence(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    groups: dict[tuple, dict[str, list[CanonicalObservation]]] = defaultdict(lambda: defaultdict(list))
    for row in observations:
        if row.variable_id != "evidence.relation_score" or not is_usable(row):
            continue
        key = (row.decision_time, row.entity_id, str(row.attributes.get("proposition_id", "__ALL__")))
        evidence_id = str(row.attributes.get("evidence_id", row.record_lineage_id))
        groups[key][evidence_id].append(row)
    output: list[AtomicFeatureRecord] = []
    for (decision_time, entity_id, proposition_id), candidates in sorted(groups.items()):
        rows = [max(items, key=lambda row: (row.available_at, row.record_lineage_id)) for items in candidates.values()]
        numeric_rows = [row for row in rows if isinstance(row.value, (int, float)) and not isinstance(row.value, bool)]
        values = [float(row.value) for row in numeric_rows]
        invalid_quality_count = sum(_source_quality(row) is None for row in numeric_rows)
        if spec.observer_id == "social.evidence_count":
            value, unit = float(len(rows)), "count"
        elif spec.observer_id == "social.evidence_balance":
            value, unit = (sum(values) / len(values) if values else None), "score"
        else:
            weighted = [(float(row.value), _source_quality(row)) for row in numeric_rows]
            valid = [(value, quality) for value, quality in weighted if quality is not None]
            denominator = sum(quality for _, quality in valid)
            value = sum(item * quality for item, quality in valid) / denominator if denominator > 0 else None
            unit = "score"
        quality_state = combine_quality(row.quality_state for row in rows)
        if invalid_quality_count and spec.observer_id == "social.evidence_quality_weighted_balance":
            quality_state = QualityState.DEGRADED
        output.append(
            one_record(
                decision_time=decision_time,
                entity_id=entity_id,
                spec=spec,
                value=value,
                unit=unit,
                available_at=max(row.available_at for row in rows),
                lineage_ids=[row.record_lineage_id for row in rows],
                modalities=[row.source_modality for row in rows],
                quality_state=quality_state,
                attributes={
                    "proposition_id": proposition_id,
                    "deduplicated_evidence_count": len(rows),
                    "invalid_source_quality_count": invalid_quality_count,
                },
            )
        )
    return output


def _disagreement(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    rows = [row for row in observations if row.variable_id == "agent.disagreement.disagreement_score" and is_usable(row)]
    return [
        one_record(
            decision_time=row.decision_time,
            entity_id=row.entity_id,
            spec=spec,
            value=float(row.value) if isinstance(row.value, (int, float)) and not isinstance(row.value, bool) else None,
            unit="score",
            available_at=row.available_at,
            lineage_ids=[row.record_lineage_id],
            modalities=[row.source_modality],
            quality_state=row.quality_state,
            attributes=row.attributes,
        )
        for row in rows
    ]


def _hypotheses(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    grouped: dict[tuple, list[CanonicalObservation]] = defaultdict(list)
    for row in observations:
        if row.variable_id == "hypothesis.active" and is_usable(row):
            grouped[(row.decision_time, row.entity_id)].append(row)
    return [
        one_record(
            decision_time=decision_time,
            entity_id=entity_id,
            spec=spec,
            value=float(len(rows)),
            unit="count",
            available_at=max(row.available_at for row in rows),
            lineage_ids=[row.record_lineage_id for row in rows],
            modalities=[row.source_modality for row in rows],
            quality_state=combine_quality(row.quality_state for row in rows),
        )
        for (decision_time, entity_id), rows in sorted(grouped.items())
    ]


def _narrative_shift(observations: tuple[CanonicalObservation, ...], spec: ObserverSpec) -> list[AtomicFeatureRecord]:
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)
    for row in observations:
        if (
            is_usable(row)
            and row.variable_id.startswith(("social.feature.", "memory.feature."))
            and isinstance(row.value, (int, float))
            and not isinstance(row.value, bool)
        ):
            grouped[(row.entity_id, row.variable_id)].append(row)
    output: list[AtomicFeatureRecord] = []
    for (entity_id, variable_id), rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: row.decision_time)
        dynamic = _copy_spec(spec, variable_id)
        for index, row in enumerate(ordered):
            dependencies = ordered[max(0, index - 1):index + 1]
            shift = float(row.value) - float(ordered[index - 1].value) if index > 0 else None
            provenance = from_observations(dependencies)
            if provenance is None:
                continue
            output.append(
                one_record(
                    decision_time=row.decision_time,
                    entity_id=entity_id,
                    spec=dynamic,
                    value=shift,
                    unit="score_change",
                    available_at=provenance.available_at,
                    lineage_ids=provenance.lineage_ids,
                    modalities=provenance.modalities,
                    quality_state=provenance.quality_state,
                    attributes={"source_variable_id": variable_id},
                )
            )
    return output


def compute(observations: tuple[CanonicalObservation, ...], specs: tuple[ObserverSpec, ...]) -> list[AtomicFeatureRecord]:
    output: list[AtomicFeatureRecord] = []
    for spec in specs:
        if spec.observer_id == "social.feature_passthrough":
            output.extend(_passthrough(observations, spec))
        elif spec.observer_id.startswith("social.evidence_"):
            output.extend(_evidence(observations, spec))
        elif spec.observer_id == "social.disagreement_state":
            output.extend(_disagreement(observations, spec))
        elif spec.observer_id == "social.hypothesis_count":
            output.extend(_hypotheses(observations, spec))
        elif spec.observer_id == "social.narrative_shift":
            output.extend(_narrative_shift(observations, spec))
    return output
