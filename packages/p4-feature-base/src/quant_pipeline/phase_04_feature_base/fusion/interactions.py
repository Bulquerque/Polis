from __future__ import annotations

import math

from ..economic_models import MissingnessState, QualityState
from ..fusion_models import (
    AlignedPerspectiveRecord,
    ApprovedInteractionRegistry,
    InteractionFeatureRecord,
    InteractionOperation,
)
from ..fusion_protocol import fusion_lineage_hash


def _quality(rows: list[AlignedPerspectiveRecord]) -> QualityState:
    if any(row.quality_state is QualityState.BLOCKED for row in rows):
        return QualityState.BLOCKED
    if any(row.quality_state is QualityState.DEGRADED for row in rows):
        return QualityState.DEGRADED
    return QualityState.PASS


def _calculate(
    operation: InteractionOperation, values: list[float], parameters: dict
) -> tuple[float | None, str]:
    if operation is InteractionOperation.SIGN_AGREEMENT:
        signs = [0 if value == 0 else (1 if value > 0 else -1) for value in values]
        return (1.0 if len(set(signs)) == 1 else -1.0), "dimensionless"
    if operation is InteractionOperation.SAFE_RATIO:
        epsilon = float(parameters["epsilon"])
        return (None, "ratio") if abs(values[1]) < epsilon else (values[0] / values[1], "ratio")
    if operation is InteractionOperation.NONNEGATIVE_GEOMETRIC_MEAN:
        if any(value < 0 for value in values):
            return None, "state_geometric_mean"
        return math.prod(values) ** (1.0 / len(values)), "state_geometric_mean"
    raise ValueError(f"unsupported interaction operation: {operation}")


def _common_fields(registry, spec, decision_time, entity_id, rows):
    return {
        "decision_time": decision_time,
        "entity_id": entity_id,
        "feature_id": spec.output_feature_id,
        "interaction_id": spec.interaction_id,
        "phenomenon_id": spec.phenomenon_id,
        "perspective_id": spec.perspective_id,
        "horizon_group": spec.horizon_group,
        "operation": spec.operation,
        "parent_feature_ids": spec.parent_feature_ids,
        "available_at": max((row.available_at for row in rows), default=decision_time),
        "source_modalities": tuple(
            sorted({modality for row in rows for modality in row.source_modalities})
        ),
        "record_lineage_id": fusion_lineage_hash(
            [registry.lineage_id, *(row.record_lineage_id for row in rows)]
        ),
    }


def _interaction_for_anchor(by_key, registry, spec, decision_time, entity_id):
    parents = [by_key.get((decision_time, entity_id, feature_id)) for feature_id in spec.parent_feature_ids]
    valid = [
        row for row in parents
        if row is not None and row.value is not None
        and row.missingness_state is MissingnessState.OBSERVED
    ]
    common = _common_fields(registry, spec, decision_time, entity_id, valid)
    if len(valid) != len(spec.parent_feature_ids):
        return InteractionFeatureRecord(
            **common,
            value=None,
            unit="unavailable",
            quality_state=QualityState.DEGRADED,
            missingness_state=MissingnessState.STRUCTURALLY_MISSING,
            attributes={"strong_heredity": True, "reason": "MISSING_PARENT"},
        )
    value, unit = _calculate(spec.operation, [float(row.value) for row in valid], spec.parameters)
    return InteractionFeatureRecord(
        **common,
        value=value,
        unit=unit,
        quality_state=_quality(valid) if value is not None else QualityState.DEGRADED,
        missingness_state=(
            MissingnessState.OBSERVED if value is not None
            else MissingnessState.STRUCTURALLY_MISSING
        ),
        attributes={"strong_heredity": True, "rationale_id": spec.rationale_id, **spec.parameters},
    )


def compute_interactions(
    records: tuple[AlignedPerspectiveRecord, ...], registry: ApprovedInteractionRegistry
) -> list[InteractionFeatureRecord]:
    by_key = {(row.decision_time, row.entity_id, row.feature_id): row for row in records}
    output: list[InteractionFeatureRecord] = []
    for spec in (row for row in registry.records if row.enabled):
        parent_set = set(spec.parent_feature_ids)
        anchors = sorted(
            {(row.decision_time, row.entity_id) for row in records if row.feature_id in parent_set}
        )
        output.extend(
            _interaction_for_anchor(by_key, registry, spec, decision_time, entity_id)
            for decision_time, entity_id in anchors
        )
    return output
