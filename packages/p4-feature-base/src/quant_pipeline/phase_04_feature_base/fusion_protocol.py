from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .artifact_protocol import stable_hash
from .economic_models import ExecutionContext, ExecutionStatus, QualityState
from .fusion_models import (
    AlignedPerspectivePanel,
    AlignedPerspectiveRecord,
    ConflictRecord,
    HorizonFeatureManifestRecord,
    HorizonFeaturePanel,
    HorizonFeatureRecord,
    HorizonFeatureSetManifest,
    InteractionFeaturePanel,
    InteractionFeatureRecord,
    PerspectiveConflictPanel,
)


def fusion_lineage_hash(values: Iterable[str]) -> str:
    unique = sorted({value for value in values if value})
    return f"lineage-p4-s6-{stable_hash(unique)[:24]}"


def _metadata(
    artifact_name: str,
    context: ExecutionContext,
    records: list[Any],
    lineage_ids: Iterable[str],
) -> dict[str, Any]:
    payload = [record.model_dump(mode="json") for record in records]
    content_hash = stable_hash({"artifact_name": artifact_name, "records": payload})
    record_lineage = (
        getattr(record, "record_lineage_id", "") for record in records
    )
    return {
        "artifact_id": f"{artifact_name}:{content_hash[:16]}",
        "schema_version": "p4.s6.v1",
        "pipeline_version": context.pipeline_version,
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": context.as_of_time,
        "created_at": context.created_at,
        "content_hash": content_hash,
        "lineage_id": fusion_lineage_hash([*lineage_ids, *record_lineage]),
    }


def build_aligned_panel(
    *,
    context: ExecutionContext,
    records: list[AlignedPerspectiveRecord],
    status: ExecutionStatus,
    quality: QualityState,
    reasons: tuple[str, ...],
    lineage_ids: Iterable[str],
) -> AlignedPerspectivePanel:
    ordered = sorted(
        records,
        key=lambda record: (
            record.decision_time,
            record.entity_id,
            record.feature_id,
            record.parameterization_id,
        ),
    )
    return AlignedPerspectivePanel(
        **_metadata("aligned_perspective_panel", context, ordered, lineage_ids),
        execution_status=status,
        quality_status=quality,
        quality_reasons=reasons,
        records=tuple(ordered),
    )


def build_conflict_panel(
    *,
    context: ExecutionContext,
    records: list[ConflictRecord],
    status: ExecutionStatus,
    quality: QualityState,
    reasons: tuple[str, ...],
    lineage_ids: Iterable[str],
) -> PerspectiveConflictPanel:
    ordered = sorted(
        records,
        key=lambda record: (record.decision_time, record.entity_id, record.group_id),
    )
    return PerspectiveConflictPanel(
        **_metadata("perspective_conflict_panel", context, ordered, lineage_ids),
        execution_status=status,
        quality_status=quality,
        quality_reasons=reasons,
        records=tuple(ordered),
    )


def build_interaction_panel(
    *,
    context: ExecutionContext,
    records: list[InteractionFeatureRecord],
    status: ExecutionStatus,
    quality: QualityState,
    reasons: tuple[str, ...],
    lineage_ids: Iterable[str],
) -> InteractionFeaturePanel:
    ordered = sorted(
        records,
        key=lambda record: (record.decision_time, record.entity_id, record.feature_id),
    )
    return InteractionFeaturePanel(
        **_metadata("interaction_feature_panel", context, ordered, lineage_ids),
        execution_status=status,
        quality_status=quality,
        quality_reasons=reasons,
        records=tuple(ordered),
    )


def build_horizon_outputs(
    *,
    context: ExecutionContext,
    records: list[HorizonFeatureRecord],
    manifest_records: list[HorizonFeatureManifestRecord],
    status: ExecutionStatus,
    quality: QualityState,
    reasons: tuple[str, ...],
    lineage_ids: Iterable[str],
) -> tuple[HorizonFeaturePanel, HorizonFeatureSetManifest]:
    ordered = sorted(
        records,
        key=lambda record: (
            record.decision_time,
            record.entity_id,
            record.horizon_group,
            record.feature_kind,
            record.feature_id,
        ),
    )
    panel = HorizonFeaturePanel(
        **_metadata("horizon_feature_panel", context, ordered, lineage_ids),
        execution_status=status,
        quality_status=quality,
        quality_reasons=reasons,
        records=tuple(ordered),
    )
    ordered_manifest = sorted(
        manifest_records,
        key=lambda record: (
            record.horizon_group,
            record.feature_kind,
            record.feature_id,
        ),
    )
    manifest = HorizonFeatureSetManifest(
        **_metadata(
            "horizon_feature_set_manifest",
            context,
            ordered_manifest,
            [panel.lineage_id],
        ),
        records=tuple(ordered_manifest),
    )
    return panel, manifest
