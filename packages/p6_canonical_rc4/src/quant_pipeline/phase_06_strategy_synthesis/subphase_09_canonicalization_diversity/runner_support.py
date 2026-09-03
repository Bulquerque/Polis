"""P6.S9 module implementations."""

from __future__ import annotations

from typing import Any

from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult
from .services import (
    add_economic_fingerprints,
    archive_coverage_report,
    add_payoff_fingerprints,
    canonicalize_candidates_with_remap,
    cluster_equivalence,
    relative_scale_records,
    select_representatives,
)


def _artifact(
    records: tuple[Any, ...],
    name: str,
    module_id: str,
    context: PhaseContext,
):
    status = (
        ArtifactStatus.COMPLETE
        if records
        else ArtifactStatus.EMPTY_VALID
    )
    return build_artifact(
        artifact_type=name,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=records,
        status=status,
    )


def canonicalize(inputs, configuration, context) -> ModuleResult:
    module_id = "P6.S9.M01"
    records, candidate_id_remap = canonicalize_candidates_with_remap(
        inputs["raw_strategy_candidate_panel"].records,
        inputs["strategy_qualification_panel"].records,
        configuration,
    )
    artifact = _artifact(
        records,
        "canonical_strategy_candidate_panel",
        module_id,
        context,
    )
    outputs = {"canonical_strategy_candidate_panel": artifact}
    for name, source in inputs.items():
        if name in {"raw_strategy_candidate_panel", "canonical_strategy_candidate_panel"}:
            continue
        source_records = getattr(source, "records", None)
        if source_records is None:
            continue
        remapped = tuple(_remap_candidate_record(record, candidate_id_remap) for record in source_records)
        if remapped != tuple(source_records):
            outputs[name] = _artifact(remapped, name, module_id, context)
    return ModuleResult(module_id=module_id, outputs=outputs)


def _remap_candidate_record(record: Any, remap: dict[str, str]) -> Any:
    candidate_id = getattr(record, "candidate_id", None)
    if candidate_id in remap and hasattr(record, "model_copy"):
        updates: dict[str, Any] = {"candidate_id": remap[candidate_id]}
        if hasattr(record, "parent_candidate_ids"):
            updates["parent_candidate_ids"] = tuple(
                remap.get(parent, parent) for parent in record.parent_candidate_ids
            )
        return record.model_copy(update=updates)
    return record


def scale(inputs, configuration, context) -> ModuleResult:
    del configuration
    module_id = "P6.S9.M02"
    records = relative_scale_records(
        inputs["canonical_strategy_candidate_panel"].records
    )
    artifact = _artifact(
        records,
        "relative_scale_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"relative_scale_panel": artifact},
    )


def payoff_fp(inputs, configuration, context) -> ModuleResult:
    del configuration
    module_id = "P6.S9.M03"
    records = add_payoff_fingerprints(
        inputs["relative_scale_panel"].records,
        inputs["strategy_payoff_panel"].records,
        inputs["canonical_strategy_candidate_panel"].records,
    )
    artifact = _artifact(
        records,
        "payoff_fingerprint_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"payoff_fingerprint_panel": artifact},
    )


def economic_fp(inputs, configuration, context) -> ModuleResult:
    del configuration
    module_id = "P6.S9.M04"
    records = add_economic_fingerprints(
        inputs["payoff_fingerprint_panel"].records,
        inputs["strategy_risk_panel"].records,
        inputs["strategy_cost_liquidity_panel"].records,
    )
    artifact = _artifact(
        records,
        "economic_fingerprint_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"economic_fingerprint_panel": artifact},
    )


def cluster(inputs, configuration, context) -> ModuleResult:
    del configuration
    module_id = "P6.S9.M05"
    records = cluster_equivalence(
        inputs["economic_fingerprint_panel"].records
    )
    artifact = _artifact(
        records,
        "candidate_equivalence_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"candidate_equivalence_panel": artifact},
    )


def representatives(inputs, configuration, context) -> ModuleResult:
    module_id = "P6.S9.M06"
    equivalence, candidates, cells = select_representatives(
        inputs["canonical_strategy_candidate_panel"].records,
        inputs["candidate_equivalence_panel"].records,
        inputs["strategy_risk_panel"].records,
        inputs["strategy_cost_liquidity_panel"].records,
        configuration,
    )
    equivalence_artifact = _artifact(
        equivalence,
        "candidate_equivalence_panel_final",
        module_id,
        context,
    )
    candidate_artifact = _artifact(
        candidates,
        "representative_strategy_candidate_panel",
        module_id,
        context,
    )
    archive_artifact = _artifact(
        cells,
        "quality_diversity_archive",
        module_id,
        context,
    )
    report = archive_coverage_report(
        cells,
        candidates,
        len(inputs["canonical_strategy_candidate_panel"].records) - len(candidates),
        configuration,
    )
    report_artifact = _artifact(
        (report,),
        "quality_diversity_report",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={
            "candidate_equivalence_panel_final": equivalence_artifact,
            "representative_strategy_candidate_panel": candidate_artifact,
            "quality_diversity_archive": archive_artifact,
            "quality_diversity_report": report_artifact,
        },
    )
