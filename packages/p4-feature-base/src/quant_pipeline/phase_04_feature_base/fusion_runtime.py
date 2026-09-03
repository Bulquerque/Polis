from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .economic_errors import ContractError
from .economic_models import ExecutionContext, ExecutionStatus, QualityState
from .fusion.alignment import align_perspectives
from .fusion.conflict import compute_conflicts
from .fusion.horizons import assemble_horizon_features
from .fusion.interactions import compute_interactions
from .fusion_models import (
    AlignedPerspectivePanel,
    InteractionFeaturePanel,
    PerspectiveConflictPanel,
)
from .fusion_protocol import (
    build_aligned_panel,
    build_conflict_panel,
    build_horizon_outputs,
    build_interaction_panel,
)
from .perspective_models import PerspectiveFeaturePanel

PERSPECTIVE_ARTIFACTS = (
    "momentum_perspective_panel",
    "reversion_relative_value_perspective_panel",
    "risk_uncertainty_stress_perspective_panel",
    "liquidity_attention_crowding_perspective_panel",
    "structure_contagion_breadth_perspective_panel",
    "macro_cycle_regime_state_perspective_panel",
    "event_surprise_seasonality_perspective_panel",
    "narrative_evidence_disagreement_perspective_panel",
    "value_quality_profitability_investment_perspective_panel",
    "carry_curve_basis_perspective_panel",
)


def _status(records: list[Any]) -> tuple[ExecutionStatus, QualityState, tuple[str, ...]]:
    if not records:
        return ExecutionStatus.DEGRADED, QualityState.DEGRADED, ("NO_OUTPUT_RECORDS",)
    degraded = any(
        getattr(record, "quality_state", QualityState.PASS) is not QualityState.PASS
        for record in records
    )
    return (
        ExecutionStatus.PRODUCED,
        QualityState.DEGRADED if degraded else QualityState.PASS,
        ("DEGRADED_RECORDS_PRESENT",) if degraded else (),
    )


def run_alignment(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
) -> AlignedPerspectivePanel:
    panels = [
        inputs[name]
        for name in PERSPECTIVE_ARTIFACTS
        if isinstance(inputs.get(name), PerspectiveFeaturePanel)
    ]
    records = [record for panel in panels for record in panel.records]
    aligned = align_perspectives(
        records=records,
        registry=inputs["approved_hypothesis_passport_registry"],
        policy=inputs["alignment_policy_registry"],
    )
    status, quality, reasons = _status(aligned)
    lineage_ids = [
        inputs["approved_hypothesis_passport_registry"].lineage_id,
        inputs["alignment_policy_registry"].lineage_id,
        *(panel.lineage_id for panel in panels),
    ]
    return build_aligned_panel(
        context=context,
        records=aligned,
        status=status,
        quality=quality,
        reasons=reasons,
        lineage_ids=lineage_ids,
    )


def run_conflict(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
) -> PerspectiveConflictPanel:
    aligned = inputs.get("aligned_perspective_panel")
    if not isinstance(aligned, AlignedPerspectivePanel):
        raise ContractError(
            "P4_S6_M02_INPUT_INVALID",
            "aligned_perspective_panel is required",
        )
    records = compute_conflicts(aligned.records, inputs["conflict_group_registry"])
    status, quality, reasons = _status(records)
    return build_conflict_panel(
        context=context,
        records=records,
        status=status,
        quality=quality,
        reasons=reasons,
        lineage_ids=[aligned.lineage_id, inputs["conflict_group_registry"].lineage_id],
    )


def run_interactions(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
) -> InteractionFeaturePanel:
    aligned = inputs.get("aligned_perspective_panel")
    if not isinstance(aligned, AlignedPerspectivePanel):
        raise ContractError(
            "P4_S6_M03_INPUT_INVALID",
            "aligned_perspective_panel is required",
        )
    records = compute_interactions(
        aligned.records,
        inputs["approved_interaction_registry"],
    )
    status, quality, reasons = _status(records)
    return build_interaction_panel(
        context=context,
        records=records,
        status=status,
        quality=quality,
        reasons=reasons,
        lineage_ids=[
            aligned.lineage_id,
            inputs["approved_interaction_registry"].lineage_id,
        ],
    )


def run_horizon_assembler(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
):
    aligned = inputs.get("aligned_perspective_panel")
    conflicts = inputs.get("perspective_conflict_panel")
    interactions = inputs.get("interaction_feature_panel")
    if not (
        isinstance(aligned, AlignedPerspectivePanel)
        and isinstance(conflicts, PerspectiveConflictPanel)
        and isinstance(interactions, InteractionFeaturePanel)
    ):
        raise ContractError(
            "P4_S6_M04_INPUT_INVALID",
            "aligned, conflict, and interaction panels are required",
        )
    records, manifest = assemble_horizon_features(
        aligned.records,
        conflicts.records,
        interactions.records,
    )
    status, quality, reasons = _status(records)
    return build_horizon_outputs(
        context=context,
        records=records,
        manifest_records=manifest,
        status=status,
        quality=quality,
        reasons=reasons,
        lineage_ids=[
            aligned.lineage_id,
            conflicts.lineage_id,
            interactions.lineage_id,
        ],
    )
