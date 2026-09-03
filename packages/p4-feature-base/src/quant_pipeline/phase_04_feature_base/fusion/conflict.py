from __future__ import annotations

from collections import defaultdict
import math

import numpy as np
from scipy.stats import entropy

from ..economic_models import MissingnessState, QualityState
from ..fusion_models import AlignedPerspectiveRecord, ConflictGroupRegistry, ConflictMode, ConflictRecord
from ..fusion_protocol import fusion_lineage_hash


def _worst_quality(rows: list[AlignedPerspectiveRecord]) -> QualityState:
    if any(row.quality_state is QualityState.BLOCKED for row in rows):
        return QualityState.BLOCKED
    if any(row.quality_state is QualityState.DEGRADED for row in rows):
        return QualityState.DEGRADED
    return QualityState.PASS


def _modalities(rows: list[AlignedPerspectiveRecord]) -> tuple[str, ...]:
    return tuple(sorted({modality for row in rows for modality in row.source_modalities}))


def _dominant_modality(rows: list[AlignedPerspectiveRecord], weights: list[float]) -> str | None:
    scores: dict[str, float] = defaultdict(float)
    for row, weight in zip(rows, weights, strict=True):
        for modality in row.source_modalities:
            scores[modality] += weight
    return max(scores, key=scores.get) if scores else None


def _signed_metrics(values: np.ndarray, weights: np.ndarray) -> tuple[float, ...]:
    signs = np.sign(values)
    total = float(weights.sum())
    consensus = float(np.dot(signs, weights) / total)
    scale = float(np.median(np.abs(values)))
    normalized = values / (scale if scale > 0 else 1.0)
    center = np.average(normalized, weights=weights)
    dispersion = float(np.sqrt(np.average((normalized - center) ** 2, weights=weights)))
    buckets = np.array(
        [weights[signs < 0].sum(), weights[signs == 0].sum(), weights[signs > 0].sum()],
        dtype=float,
    )
    buckets = buckets[buckets > 0]
    ent = float(entropy(buckets, base=2) / math.log2(3)) if len(buckets) > 1 else 0.0
    positive, negative = float(weights[signs > 0].sum()), float(weights[signs < 0].sum())
    minority = min(positive, negative) / total if positive > 0 and negative > 0 else 0.0
    return consensus, 1.0 - abs(consensus), dispersion, ent, minority


def _magnitude_metrics(values: np.ndarray, weights: np.ndarray) -> tuple[float, ...]:
    transformed = np.log1p(np.abs(values))
    mean = float(np.average(transformed, weights=weights))
    dispersion = float(np.sqrt(np.average((transformed - mean) ** 2, weights=weights)))
    consensus = 1.0 / (1.0 + dispersion)
    mass = transformed * weights
    ent = float(entropy(mass, base=2) / math.log2(len(mass))) if len(mass) > 1 and mass.sum() > 0 else 0.0
    minority = float(np.min(weights) / np.sum(weights)) if len(weights) > 1 else 0.0
    return consensus, 1.0 - consensus, dispersion, ent, minority


def _observed_members(by_key, spec, decision_time, entity_id):
    rows, weights, groups, multipliers = [], [], set(), []
    for member in spec.members:
        row = by_key.get((decision_time, entity_id, member.feature_id))
        if row is None or row.value is None or row.missingness_state is not MissingnessState.OBSERVED:
            continue
        rows.append(row)
        weights.append(member.weight)
        groups.add(member.independence_group)
        multipliers.append(member.direction_multiplier)
    return rows, weights, groups, multipliers


def _common_fields(registry, spec, decision_time, entity_id, rows, weights, groups):
    return {
        "decision_time": decision_time,
        "entity_id": entity_id,
        "group_id": spec.group_id,
        "output_prefix": spec.output_prefix,
        "phenomenon_id": spec.phenomenon_id,
        "horizon_group": spec.horizon_group,
        "mode": spec.mode,
        "available_view_count": len(rows),
        "independent_view_count": len(groups),
        "expected_view_count": len(spec.members),
        "dominant_modality": _dominant_modality(rows, weights),
        "available_at": max((row.available_at for row in rows), default=decision_time),
        "source_modalities": _modalities(rows),
        "record_lineage_id": fusion_lineage_hash(
            [registry.lineage_id, *(row.record_lineage_id for row in rows)]
        ),
        "source_feature_ids": tuple(row.feature_id for row in rows),
    }


def _conflict_for_anchor(by_key, registry, spec, decision_time, entity_id) -> ConflictRecord:
    rows, weights, groups, multipliers = _observed_members(
        by_key, spec, decision_time, entity_id
    )
    common = _common_fields(registry, spec, decision_time, entity_id, rows, weights, groups)
    if len(rows) < spec.min_views:
        return ConflictRecord(
            **common,
            consensus_score=None,
            conflict_score=None,
            dispersion_score=None,
            entropy_score=None,
            minority_view_strength=None,
            quality_state=QualityState.DEGRADED,
            missingness_state=MissingnessState.STRUCTURALLY_MISSING,
            attributes={"reason": "INSUFFICIENT_COMPARABLE_VIEWS"},
        )
    values = np.array(
        [float(row.value) * multiplier for row, multiplier in zip(rows, multipliers, strict=True)],
        dtype=float,
    )
    weight_array = np.array(weights, dtype=float)
    metrics = (
        _signed_metrics(values, weight_array)
        if spec.mode is ConflictMode.SIGNED_DIRECTIONAL
        else _magnitude_metrics(values, weight_array)
    )
    return ConflictRecord(
        **common,
        consensus_score=metrics[0],
        conflict_score=metrics[1],
        dispersion_score=metrics[2],
        entropy_score=metrics[3],
        minority_view_strength=metrics[4],
        quality_state=_worst_quality(rows),
        missingness_state=MissingnessState.OBSERVED,
        attributes={"weights": weights},
    )


def compute_conflicts(
    records: tuple[AlignedPerspectiveRecord, ...], registry: ConflictGroupRegistry
) -> list[ConflictRecord]:
    by_key = {(row.decision_time, row.entity_id, row.feature_id): row for row in records}
    output: list[ConflictRecord] = []
    for spec in (row for row in registry.records if row.enabled):
        anchors = sorted(
            {(row.decision_time, row.entity_id) for row in records if row.horizon_group == spec.horizon_group}
        )
        output.extend(
            _conflict_for_anchor(by_key, registry, spec, decision_time, entity_id)
            for decision_time, entity_id in anchors
        )
    return output
