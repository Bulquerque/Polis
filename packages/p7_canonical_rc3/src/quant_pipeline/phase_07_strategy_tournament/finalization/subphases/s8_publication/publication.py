"""Strict content-reference publication for the P7→P8 V2 boundary."""
from __future__ import annotations

from dataclasses import dataclass

from ...artifacts import artifact_reference, sha256_value
from ...boundary.base import ArtifactEnvelope, ArtifactReference
from ...boundary.inputs import StrategyReferenceRecord
from ...boundary.s8_config import PublicationPolicy
from ...boundary.s8_outputs import (
    ExecutionContextSnapshotRecord,
    LegacyProjectionRecord,
    Phase8ManifestRecord,
    RankedStrategyRecord,
)
from ...errors import ErrorContext, IntegrityViolation


@dataclass(frozen=True, slots=True)
class PublicationOutputs:
    snapshots: tuple[ExecutionContextSnapshotRecord, ...]
    legacy: tuple[LegacyProjectionRecord, ...]


def _strategy_candidate_reference(strategy: StrategyReferenceRecord) -> ArtifactReference:
    if strategy.strategy_candidate_reference is not None:
        return strategy.strategy_candidate_reference
    return ArtifactReference(
        artifact_name="strategy_candidate_panel",
        artifact_id=strategy.strategy_artifact_id,
        content_sha256=strategy.strategy_content_sha256,
        schema_version=strategy.strategy_schema_version,
        record_count=1,
    )


def _required_references(strategy: StrategyReferenceRecord, policy: PublicationPolicy) -> dict[str, ArtifactReference]:
    values: dict[str, ArtifactReference | None] = {
        "strategy_candidate_reference": _strategy_candidate_reference(strategy),
        "strategy_legs_reference": strategy.strategy_legs_reference,
        "payoff_evaluation_reference": strategy.payoff_evaluation_reference,
        "scenario_evaluation_reference": strategy.scenario_evaluation_reference,
        "risk_reference": strategy.risk_reference,
        "cost_liquidity_reference": strategy.cost_liquidity_reference,
        "greeks_reference": strategy.greeks_reference,
        "generation_trace_reference": strategy.generation_trace_reference,
    }
    missing = [name for name in policy.required_reference_fields if values[name] is None]
    if missing:
        context = ErrorContext("P7.S8.M03", candidate_ids=(strategy.candidate_id,), details={"missing": missing})
        raise IntegrityViolation("P7_CONTEXT_JOIN_MISSING", ",".join(missing), context)
    return {name: value for name, value in values.items() if value is not None}


def _legacy_status(strategy: StrategyReferenceRecord, policy: PublicationPolicy) -> LegacyProjectionRecord:
    if len(strategy.leg_ids) != 1:
        status, reason = "UNSUPPORTED_MULTI_LEG", "P7_LEGACY_PROJECTION_UNSUPPORTED_MULTI_LEG"
    else:
        required = (
            strategy.legacy_underlying,
            strategy.legacy_instrument_type,
            strategy.legacy_action_type,
            strategy.legacy_reference_price,
            strategy.legacy_contract_key,
            strategy.legacy_expiration_date,
            strategy.legacy_dte,
            strategy.legacy_cost_estimate,
            strategy.legacy_liquidity_score,
        )
        status, reason = ("SUPPORTED", None) if all(value is not None for value in required) else ("UNAVAILABLE_CONTEXT", "P7_CONTEXT_JOIN_MISSING")
    return LegacyProjectionRecord(
        cycle_id=strategy.cycle_id,
        decision_time=strategy.decision_time,
        candidate_id=strategy.candidate_id,
        projection_status=status,
        reason_code=reason,
        represented_leg_count=max(1, len(strategy.leg_ids)),
        policy_version=policy.policy_id,
        lineage_id=strategy.strategy_lineage_id,
    )


def build_publication_outputs(
    ranked: tuple[RankedStrategyRecord, ...],
    strategies: dict[str, StrategyReferenceRecord],
    thesis_artifact: ArtifactEnvelope,
    decomposition_artifact: ArtifactEnvelope,
    policy: PublicationPolicy,
) -> PublicationOutputs:
    snapshots: list[ExecutionContextSnapshotRecord] = []
    legacy: list[LegacyProjectionRecord] = []
    thesis_ref = artifact_reference(thesis_artifact)
    decomposition_ref = artifact_reference(decomposition_artifact)
    for item in sorted(ranked, key=lambda row: (row.comparison_group_id, row.rank_position)):
        strategy = strategies.get(item.candidate_id)
        if strategy is None:
            raise IntegrityViolation("P7_CONTEXT_JOIN_MISSING", item.candidate_id, ErrorContext("P7.S8.M03"))
        refs = _required_references(strategy, policy)
        snapshots.append(ExecutionContextSnapshotRecord(
            cycle_id=item.cycle_id,
            decision_time=item.decision_time,
            candidate_id=item.candidate_id,
            rank_position=item.rank_position,
            comparison_group_id=item.comparison_group_id,
            strategy_candidate_reference=refs["strategy_candidate_reference"],
            strategy_legs_reference=refs["strategy_legs_reference"],
            payoff_evaluation_reference=refs["payoff_evaluation_reference"],
            scenario_evaluation_reference=refs["scenario_evaluation_reference"],
            risk_reference=refs["risk_reference"],
            cost_liquidity_reference=refs["cost_liquidity_reference"],
            greeks_reference=refs["greeks_reference"],
            generation_trace_reference=refs["generation_trace_reference"],
            thesis_card_reference=thesis_ref,
            score_decomposition_reference=decomposition_ref,
            leg_ids=strategy.leg_ids,
            lineage_id=strategy.strategy_lineage_id,
        ))
        legacy.append(_legacy_status(strategy, policy))
    return PublicationOutputs(tuple(snapshots), tuple(legacy))


def phase8_manifest_record(
    artifacts: tuple[ArtifactEnvelope, ...],
    candidate_ids: tuple[str, ...],
    policy: PublicationPolicy,
    created_at,
    lineage_id: str,
) -> Phase8ManifestRecord:
    references = tuple(sorted((artifact_reference(item) for item in artifacts), key=lambda ref: ref.artifact_name))
    conservation = sha256_value({"ranked_candidate_ids": sorted(candidate_ids)})
    return Phase8ManifestRecord(
        contract_id="p7_to_p8_strategy_ranking_handoff",
        contract_version=policy.contract_version,
        semantic_version=policy.semantic_version,
        producer_phase="P7",
        consumer_phase=policy.consumer_phase,
        artifact_references=references,
        candidate_count=len(candidate_ids),
        candidate_conservation_sha256=conservation,
        created_at=created_at,
        lineage_id=lineage_id,
    )
