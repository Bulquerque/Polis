"""Final qualification, canonical publication, lineage, and P7 handoff."""

from __future__ import annotations

from typing import Any

from ..boundaries.p7_v1 import LegacyProjection, project_legacy_records
from ..domain.identity import candidate_id as build_candidate_id
from ..domain.models import (
    ArtifactReference,
    GenerationAudit,
    Phase7StrategyHandoffManifest,
    StrategyCandidate,
    StrategyLegRecord,
    StrategyLineageRecord,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import canonical_sha256, stable_id

PUBLISHED_ARTIFACT_NAMES = (
    "strategy_candidate_panel",
    "strategy_leg_panel",
    "strategy_market_snapshot",
    "strategy_payoff_panel",
    "strategy_scenario_evaluation_panel",
    "strategy_ambiguity_evaluation_panel",
    "strategy_greek_panel",
    "strategy_risk_panel",
    "strategy_cost_liquidity_panel",
    "strategy_lineage_panel",
    "strategy_generation_trace_panel",
    "candidate_equivalence_panel",
    "quality_diversity_archive",
    "candidate_rejection_report",
    "candidate_generation_audit",
    "target_payoff_panel",
    "target_payoff_qualification_report",
    "mutation_application_panel",
    "solver_result_panel",
    "pathwise_valuation_panel",
    "quality_diversity_report",
    "candidate_feature_base_panel",
    "candidate_universe_panel",
    "option_instrument_feature_panel",
    "contract_existence_report",
    "option_feature_quality_report",
    "candidate_generation_log",
)


def filter_records(
    artifact: Any,
    candidate_ids: set[str],
) -> tuple[Any, ...]:
    return tuple(
        record
        for record in artifact.records
        if getattr(record, "candidate_id", None) in candidate_ids
    )


def canonical_publication_records(
    state: dict[str, Any],
) -> tuple[
    tuple[StrategyCandidate, ...],
    set[str],
    tuple[StrategyLegRecord, ...],
    tuple[StrategyLineageRecord, ...],
]:
    candidates = tuple(state["representative_strategy_candidate_panel"].records)
    strategy_policy_version = state.get("strategy_identity_policy_registry")
    policy_version = "wave2-strategy-v1"
    if strategy_policy_version is not None and strategy_policy_version.records:
        policy_version = strategy_policy_version.records[0].policy_version
    for candidate in candidates:
        expected_id = build_candidate_id(
            underlying_id=candidate.underlying_id,
            decision_time=candidate.decision_time.isoformat(),
            legs=candidate.legs,
            objective_family=candidate.objective_family.value,
            policy_version=policy_version,
            horizon_days=candidate.horizon_days,
        )
        if candidate.candidate_id != expected_id:
            raise ValueError("P6_CANDIDATE_IDENTITY_MISMATCH")
    candidate_ids = {
        item.candidate_id
        for item in candidates
    }
    legs = tuple(
        StrategyLegRecord(
            candidate_id=candidate.candidate_id,
            leg=leg,
        )
        for candidate in candidates
        for leg in candidate.legs
    )
    snapshot_id = state["strategy_market_snapshot"].artifact_id
    advanced_sources = (
        state["mutation_application_panel"].artifact_id,
        state["target_payoff_panel"].artifact_id,
        state["solver_result_panel"].artifact_id,
    )
    lineage = tuple(
        StrategyLineageRecord(
            candidate_id=candidate.candidate_id,
            lineage_id=candidate.lineage_id,
            source_artifact_ids=(snapshot_id,) + advanced_sources,
            generation_run_id=candidate.generation_run_id,
            origin_template_id=candidate.origin_template_id,
        )
        for candidate in candidates
    )
    return candidates, candidate_ids, legs, lineage


def build_manifest(
    state: dict[str, Any],
    candidates: tuple[StrategyCandidate, ...],
    configuration: Phase6RunConfiguration,
) -> Phase7StrategyHandoffManifest:
    references = tuple(
        _artifact_reference(name, state[name])
        for name in PUBLISHED_ARTIFACT_NAMES
        if name in state
    )
    candidate_ids = tuple(
        sorted(item.candidate_id for item in candidates)
    )
    snapshot = state["strategy_market_snapshot"].records[0]
    return Phase7StrategyHandoffManifest(
        handoff_id=stable_id(
            "p7-strategy-handoff",
            configuration.run_id,
            candidate_ids,
            references,
        ),
        decision_time=configuration.decision_time,
        cycle_id=configuration.cycle_id,
        candidate_count=len(candidate_ids),
        snapshot_hash=snapshot.snapshot_sha256,
        generation_policy_version="|".join((
            configuration.strategy.policy_version,
            configuration.mutation.policy_version,
            configuration.target_payoff.policy_version,
            configuration.solver.policy_version,
        )),
        artifact_references=references,
        candidate_ids_sha256=canonical_sha256(candidate_ids),
        production_promotion_allowed=False,
    )


def _artifact_reference(
    artifact_type: str,
    artifact: Any,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_type=artifact_type,
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        record_count=artifact.record_count,
        schema_version=artifact.schema_version,
    )


def generation_audit(
    state: dict[str, Any],
    configuration: Phase6RunConfiguration,
    published_count: int,
) -> GenerationAudit:
    raw_count = state["raw_strategy_candidate_panel"].record_count
    qualified_count = sum(
        1
        for item in state["strategy_qualification_panel"].records
        if item.qualified
    )
    canonical_count = state["canonical_strategy_candidate_panel"].record_count
    rejected_count = sum(
        state[name].record_count
        for name in (
            "contract_rejection_report",
            "template_generation_rejection_report",
            "feasibility_rejection_report",
            "mutation_rejection_report",
        )
    )
    return GenerationAudit(
        generation_run_id=configuration.run_id,
        attempted_count=raw_count + rejected_count,
        generated_count=raw_count,
        rejected_count=rejected_count,
        duplicate_count=max(0, qualified_count - canonical_count),
        qualified_count=qualified_count,
        published_count=published_count,
        seed=configuration.seed,
        policy_version=configuration.strategy.policy_version,
    )


def legacy_projection(
    state: dict[str, Any],
    candidates: tuple[StrategyCandidate, ...],
    configuration: Phase6RunConfiguration,
) -> LegacyProjection:
    candidate_ids = {
        item.candidate_id
        for item in candidates
    }
    risks = filter_records(
        state["strategy_risk_panel"],
        candidate_ids,
    )
    greeks = filter_records(
        state["strategy_greek_panel"],
        candidate_ids,
    )
    qualifications = filter_records(
        state["strategy_qualification_panel"],
        candidate_ids,
    )
    return project_legacy_records(
        candidates,
        risks,
        greeks,
        qualifications,
        state["validated_market_belief_state"].records,
        configuration.decision_time,
    )
