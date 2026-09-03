"""Canonical materialization helpers for strategy mutations."""

from __future__ import annotations

from ..domain.enums import MutationOperator, OriginMode
from ..domain.identity import candidate_id
from ..domain.models import (
    CandidateGenerationTrace,
    MutationApplication,
    StrategyCandidate,
    StrategyLeg,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id

MutatedPair = tuple[StrategyCandidate, MutationApplication]


def build_child(
    parent: StrategyCandidate,
    legs: tuple[StrategyLeg, ...],
    operator: MutationOperator,
    parameters: dict[str, str],
    configuration: Phase6RunConfiguration,
) -> MutatedPair:
    """Build a deterministic child and its mutation application."""
    identifier = candidate_id(
        underlying_id=parent.underlying_id,
        decision_time=parent.decision_time.isoformat(),
        legs=legs,
        objective_family=parent.objective_family.value,
        policy_version=configuration.mutation.policy_version,
        horizon_days=parent.horizon_days,
    )
    child = parent.model_copy(
        update={
            "candidate_id": identifier,
            "candidate_version": "2",
            "origin_mode": OriginMode.MUTATION,
            "parent_candidate_ids": (parent.candidate_id,),
            "mutation_trace": parent.mutation_trace + (operator.value,),
            "legs": legs,
            "lineage_id": stable_id(
                "mutation-lineage",
                parent.lineage_id,
                identifier,
                operator,
            ),
        }
    )
    application = MutationApplication(
        mutation_id=stable_id(
            "mutation",
            parent.candidate_id,
            identifier,
            operator,
            parameters,
        ),
        parent_candidate_id=parent.candidate_id,
        child_candidate_id=identifier,
        operator=operator,
        parameters=parameters,
        application_index=len(parent.mutation_trace) + 1,
        valid=True,
    )
    return child, application


def build_trace(
    parent: StrategyCandidate,
    child: StrategyCandidate,
    application: MutationApplication,
) -> CandidateGenerationTrace:
    """Build the immutable genealogy record for a child candidate."""
    return CandidateGenerationTrace(
        candidate_id=child.candidate_id,
        origin=OriginMode.MUTATION,
        origin_template_id=child.origin_template_id,
        parent_candidate_ids=(parent.candidate_id,),
        operators=(application.operator.value,),
        parameters={
            "mutation_id": application.mutation_id,
            **application.parameters,
        },
        generation_stage="P6.S4",
    )
