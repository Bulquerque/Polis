from __future__ import annotations

from collections import defaultdict

from ..economic_models import MissingnessState, QualityState
from ..fusion_models import (
    AlignedPerspectiveRecord,
    ConflictRecord,
    FeatureKind,
    HorizonFeatureManifestRecord,
    HorizonFeatureRecord,
    InteractionFeatureRecord,
)

CONFLICT_METRICS = (
    "consensus_score",
    "conflict_score",
    "dispersion_score",
    "entropy_score",
    "minority_view_strength",
)


def _age_seconds(decision_time, available_at) -> float:
    return max(0.0, (decision_time - available_at).total_seconds())


def _perspective_rows(records: tuple[AlignedPerspectiveRecord, ...]) -> list[HorizonFeatureRecord]:
    return [
        HorizonFeatureRecord(
            decision_time=row.decision_time,
            entity_id=row.entity_id,
            feature_id=row.feature_id,
            feature_kind=FeatureKind.PERSPECTIVE,
            phenomenon_id=row.phenomenon_id,
            horizon_group=row.horizon_group,
            value=row.value,
            unit=row.unit,
            available_at=row.available_at,
            information_age_seconds=_age_seconds(row.decision_time, row.available_at),
            is_observed=row.value is not None and row.missingness_state is MissingnessState.OBSERVED,
            quality_state=row.quality_state,
            missingness_state=row.missingness_state,
            source_feature_ids=row.source_feature_ids,
            source_modalities=row.source_modalities,
            record_lineage_id=row.record_lineage_id,
            attributes={
                "hypothesis_id": row.hypothesis_id,
                "perspective_id": row.perspective_id,
                "observer_id": row.observer_id,
                "parameterization_id": row.parameterization_id,
                "source_decision_time": row.source_decision_time.isoformat() if row.source_decision_time else None,
                "source_modalities": row.source_modalities,
                **row.attributes,
            },
        )
        for row in records
    ]


def _conflict_rows(records: tuple[ConflictRecord, ...]) -> list[HorizonFeatureRecord]:
    output: list[HorizonFeatureRecord] = []
    for row in records:
        for metric in CONFLICT_METRICS:
            value = getattr(row, metric)
            output.append(
                HorizonFeatureRecord(
                    decision_time=row.decision_time,
                    entity_id=row.entity_id,
                    feature_id=f"{row.output_prefix}.{metric.removesuffix('_score')}",
                    feature_kind=FeatureKind.CONFLICT,
                    phenomenon_id=row.phenomenon_id,
                    horizon_group=row.horizon_group,
                    value=value,
                    unit="dimensionless",
                    available_at=row.available_at,
                    information_age_seconds=_age_seconds(row.decision_time, row.available_at),
                    is_observed=value is not None,
                    quality_state=row.quality_state,
                    missingness_state=(row.missingness_state if value is None else MissingnessState.OBSERVED),
                    source_feature_ids=row.source_feature_ids,
                    source_modalities=row.source_modalities,
                    record_lineage_id=row.record_lineage_id,
                    attributes={
                        "group_id": row.group_id,
                        "mode": row.mode.value,
                        "available_view_count": row.available_view_count,
                        "independent_view_count": row.independent_view_count,
                        "expected_view_count": row.expected_view_count,
                        "dominant_modality": row.dominant_modality,
                    },
                )
            )
    return output


def _interaction_rows(records: tuple[InteractionFeatureRecord, ...]) -> list[HorizonFeatureRecord]:
    return [
        HorizonFeatureRecord(
            decision_time=row.decision_time,
            entity_id=row.entity_id,
            feature_id=row.feature_id,
            feature_kind=FeatureKind.INTERACTION,
            phenomenon_id=row.phenomenon_id,
            horizon_group=row.horizon_group,
            value=row.value,
            unit=row.unit,
            available_at=row.available_at,
            information_age_seconds=_age_seconds(row.decision_time, row.available_at),
            is_observed=row.value is not None,
            quality_state=row.quality_state,
            missingness_state=row.missingness_state,
            source_feature_ids=row.parent_feature_ids,
            source_modalities=row.source_modalities,
            record_lineage_id=row.record_lineage_id,
            attributes={
                "interaction_id": row.interaction_id,
                "perspective_id": row.perspective_id,
                "operation": row.operation.value,
                **row.attributes,
            },
        )
        for row in records
    ]


def assemble_horizon_features(
    aligned: tuple[AlignedPerspectiveRecord, ...],
    conflicts: tuple[ConflictRecord, ...],
    interactions: tuple[InteractionFeatureRecord, ...],
) -> tuple[list[HorizonFeatureRecord], list[HorizonFeatureManifestRecord]]:
    records = [*_perspective_rows(aligned), *_conflict_rows(conflicts), *_interaction_rows(interactions)]
    groups: dict[tuple, list[HorizonFeatureRecord]] = defaultdict(list)
    for row in records:
        groups[(row.feature_id, row.feature_kind, row.phenomenon_id, row.horizon_group)].append(row)
    manifest: list[HorizonFeatureManifestRecord] = []
    for (feature_id, kind, phenomenon, horizon), rows in groups.items():
        total = len(rows)
        observed = sum(row.is_observed for row in rows)
        ages = [row.information_age_seconds for row in rows if row.information_age_seconds is not None]
        quality = (
            QualityState.BLOCKED
            if any(row.quality_state is QualityState.BLOCKED for row in rows)
            else QualityState.DEGRADED
            if any(row.quality_state is QualityState.DEGRADED for row in rows)
            else QualityState.PASS
        )
        manifest.append(
            HorizonFeatureManifestRecord(
                feature_id=feature_id,
                feature_kind=kind,
                phenomenon_id=phenomenon,
                horizon_group=horizon,
                source_feature_ids=tuple(
                    sorted(set().union(*(set(row.source_feature_ids) for row in rows)))
                ),
                total_record_count=total,
                observed_record_count=observed,
                coverage_rate=observed / total if total else 0.0,
                first_decision_time=min(row.decision_time for row in rows) if rows else None,
                last_decision_time=max(row.decision_time for row in rows) if rows else None,
                maximum_information_age_seconds=max(ages) if ages else None,
                quality_state=quality,
            )
        )
    return records, manifest
