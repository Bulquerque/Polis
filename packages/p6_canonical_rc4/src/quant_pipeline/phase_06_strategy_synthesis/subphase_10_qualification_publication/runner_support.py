"""P6.S10 qualification, publication, V1 projection, and handoff runner."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import chain
from typing import Any

from ..domain.models import LegacyHandoffManifest, StrategyCandidate
from ..foundation.artifacts import ArtifactEnvelope, ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.hashing import stable_id
from ..foundation.results import ModuleResult, SubphaseResult
from .services import (
    build_manifest,
    canonical_publication_records,
    filter_records,
    generation_audit,
    legacy_projection,
)

_CANONICAL_OUTPUTS = (
    "strategy_candidate_panel",
    "strategy_leg_panel",
    "strategy_payoff_panel",
    "strategy_scenario_evaluation_panel",
    "strategy_ambiguity_evaluation_panel",
    "strategy_greek_panel",
    "strategy_risk_panel",
    "strategy_cost_liquidity_panel",
    "strategy_lineage_panel",
    "strategy_generation_trace_panel",
    "candidate_equivalence_panel",
    "candidate_rejection_report",
    "candidate_generation_audit",
)

_FILTERED_SOURCE_OUTPUTS = (
    "strategy_payoff_panel",
    "strategy_scenario_evaluation_panel",
    "strategy_ambiguity_evaluation_panel",
    "strategy_greek_panel",
    "strategy_risk_panel",
    "strategy_cost_liquidity_panel",
    "strategy_generation_trace_panel",
)

_LEGACY_OUTPUTS = (
    "candidate_feature_base_panel",
    "candidate_universe_panel",
    "option_instrument_feature_panel",
    "contract_existence_report",
    "option_feature_quality_report",
    "candidate_generation_log",
)


def _artifact(
    *,
    records: Iterable[Any],
    artifact_type: str,
    module_id: str,
    context: PhaseContext,
    input_artifact_ids: Iterable[str] = (),
    status: ArtifactStatus | None = None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactEnvelope[Any]:
    return build_artifact(
        artifact_type=artifact_type,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=records,
        input_artifact_ids=input_artifact_ids,
        status=status,
        metadata=metadata,
    )


def _records_status(records: Iterable[Any]) -> ArtifactStatus:
    return ArtifactStatus.COMPLETE if tuple(records) else ArtifactStatus.EMPTY_VALID


def publish_canonical_outputs(
    state: dict[str, Any],
    context: PhaseContext,
    configuration: Any,
) -> ModuleResult:
    module_id = "P6.S10.M01"
    candidates, candidate_ids, legs, lineage = canonical_publication_records(state)
    _publish_identity_panels(state, context, module_id, candidates, legs, lineage)
    _publish_filtered_panels(state, context, module_id, candidate_ids)
    _publish_rejections_and_audit(
        state,
        context,
        module_id,
        configuration,
        len(candidates),
    )
    outputs = {name: state[name] for name in _CANONICAL_OUTPUTS}
    return ModuleResult(module_id=module_id, outputs=outputs)


def _publish_identity_panels(
    state: dict[str, Any],
    context: PhaseContext,
    module_id: str,
    candidates: tuple[Any, ...],
    legs: tuple[Any, ...],
    lineage: tuple[Any, ...],
) -> None:
    publication_status = _records_status(candidates)
    state["strategy_candidate_panel"] = _artifact(
        records=candidates,
        artifact_type="strategy_candidate_panel",
        module_id=module_id,
        context=context,
        status=publication_status,
    )
    state["strategy_leg_panel"] = _artifact(
        records=legs,
        artifact_type="strategy_leg_panel",
        module_id=module_id,
        context=context,
        status=_records_status(legs),
    )
    state["strategy_lineage_panel"] = _artifact(
        records=lineage,
        artifact_type="strategy_lineage_panel",
        module_id=module_id,
        context=context,
        status=publication_status,
    )


def _publish_filtered_panels(
    state: dict[str, Any],
    context: PhaseContext,
    module_id: str,
    candidate_ids: set[str],
) -> None:
    for artifact_name in _FILTERED_SOURCE_OUTPUTS:
        source = state[artifact_name]
        records = filter_records(source, candidate_ids)
        status = _records_status(records)
        if records and source.status in {ArtifactStatus.DEGRADED, ArtifactStatus.BLOCKED}:
            status = source.status
        state[artifact_name] = _artifact(
            records=records,
            artifact_type=artifact_name,
            module_id=module_id,
            context=context,
            input_artifact_ids=(source.artifact_id,),
            status=status,
        )
    state["candidate_equivalence_panel"] = state[
        "candidate_equivalence_panel_final"
    ]


def _publish_rejections_and_audit(
    state: dict[str, Any],
    context: PhaseContext,
    module_id: str,
    configuration: Any,
    published_count: int,
) -> None:
    rejections = tuple(
        chain(
            state["contract_rejection_report"].records,
            state["template_generation_rejection_report"].records,
            state["feasibility_rejection_report"].records,
            state["mutation_rejection_report"].records,
        )
    )
    state["candidate_rejection_report"] = _artifact(
        records=rejections,
        artifact_type="candidate_rejection_report",
        module_id=module_id,
        context=context,
        status=_records_status(rejections),
    )
    audit = generation_audit(state, configuration, published_count)
    state["candidate_generation_audit"] = _artifact(
        records=(audit,),
        artifact_type="candidate_generation_audit",
        module_id=module_id,
        context=context,
    )


def publish_legacy_projection(
    state: dict[str, Any],
    context: PhaseContext,
    configuration: Any,
) -> ModuleResult:
    module_id = "P6.S10.M02"
    candidates = tuple(state["strategy_candidate_panel"].records)
    (
        feature_records,
        universe_records,
        option_records,
        quality_records,
        log_records,
    ) = legacy_projection(state, candidates, configuration)
    status = _records_status(candidates)

    records_by_artifact = {
        "candidate_feature_base_panel": feature_records,
        "candidate_universe_panel": universe_records,
        "option_instrument_feature_panel": option_records,
        "contract_existence_report": quality_records,
        "option_feature_quality_report": quality_records,
        "candidate_generation_log": log_records,
    }
    legacy_outputs: dict[str, ArtifactEnvelope[Any]] = {}
    for artifact_name, records in records_by_artifact.items():
        metadata = (
            {"projection": "P7_V1_LIMITED"}
            if artifact_name == "candidate_feature_base_panel"
            else None
        )
        legacy_outputs[artifact_name] = _artifact(
            records=records,
            artifact_type=artifact_name,
            module_id=module_id,
            context=context,
            status=status,
            metadata=metadata,
        )

    state.update(legacy_outputs)
    return ModuleResult(module_id=module_id, outputs=legacy_outputs)


def _legacy_handoff_manifest(
    state: dict[str, Any],
    context: PhaseContext,
    candidates: tuple[StrategyCandidate, ...],
) -> ArtifactEnvelope[LegacyHandoffManifest]:
    candidate_ids = tuple(sorted(item.candidate_id for item in candidates))
    record = LegacyHandoffManifest(
        handoff_id=stable_id("legacy-p7-handoff", context.run_id, candidate_ids),
        candidate_id=candidate_ids[0] if candidate_ids else "EMPTY_VALID",
        created_at=context.created_at,
        target_phase="P7",
        candidate_count=len(candidate_ids),
        artifact_ids=tuple(state[name].artifact_id for name in _LEGACY_OUTPUTS),
        lineage_id=stable_id("legacy-lineage", context.run_id, _LEGACY_OUTPUTS),
        pipeline_version="P6-RC6.2-P5-V2-CLOSURE-RC4",
    )
    return _artifact(
        records=(record,),
        artifact_type="phase7_candidate_handoff_manifest",
        module_id="P6.S10.M03",
        context=context,
        status=ArtifactStatus.COMPLETE,
    )


def publish_handoffs(
    state: dict[str, Any],
    context: PhaseContext,
    configuration: Any,
) -> ModuleResult:
    module_id = "P6.S10.M03"
    candidates = tuple(state["strategy_candidate_panel"].records)
    manifest = build_manifest(state, candidates, configuration)
    outputs: dict[str, ArtifactEnvelope[Any]] = {
        "phase7_strategy_handoff_manifest": _artifact(
            records=(manifest,),
            artifact_type="phase7_strategy_handoff_manifest",
            module_id=module_id,
            context=context,
        )
    }
    if configuration.publication.publish_legacy_p7_projection:
        outputs["phase7_candidate_handoff_manifest"] = _legacy_handoff_manifest(
            state,
            context,
            candidates,
        )

    state.update(outputs)
    return ModuleResult(module_id=module_id, outputs=outputs)

