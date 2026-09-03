from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus
from quant_pipeline.phase_09.subphases.s10_memory_release import (
    P3ContextState,
    normalize_matured_research_memory,
    update_research_memory_and_build_p3_handoff,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.models import (
    ResearchMemoryUpdatePolicy,
    ResearchNormalizationPolicy,
)

from tests.s10.conftest import NOW, SOURCE_CYCLE, research_candidates


def normalized(candidates=None):
    result = normalize_matured_research_memory(
        candidates=candidates or research_candidates()[:3],
        policy=ResearchNormalizationPolicy(policy_id="normalization"),
    )
    assert result.output is not None
    return result.output


def test_updates_memory_and_builds_safe_p3_context() -> None:
    result = update_research_memory_and_build_p3_handoff(
        normalized=normalized(),
        previous_snapshot=None,
        policy=ResearchMemoryUpdatePolicy(policy_id="memory"),
        current_cycle=SOURCE_CYCLE,
        created_at=NOW,
    )
    assert result.output is not None
    assert result.output.p3_handoff.state == P3ContextState.P3_CONTEXT_READY
    assert result.output.p3_handoff.context_items
    assert not result.output.p3_handoff.world_memory_write_allowed
    assert all(
        not item.world_memory_write_allowed
        for item in result.output.p3_handoff.context_items
    )


def test_blocks_private_or_future_details_from_p3() -> None:
    blocked = research_candidates()[0].model_copy(
        update={
            "candidate_id": "blocked",
            "semantic_key": "blocked-key",
            "contains_future_outcome_identifiers": True,
        }
    )
    result = update_research_memory_and_build_p3_handoff(
        normalized=normalized((blocked,)),
        previous_snapshot=None,
        policy=ResearchMemoryUpdatePolicy(policy_id="memory"),
        current_cycle=SOURCE_CYCLE,
        created_at=NOW,
    )
    assert result.output is not None
    assert result.output.p3_handoff.state == P3ContextState.TEMPORAL_LEAKAGE_BLOCKED
    assert result.output.p3_handoff.blocked_memory_item_ids


def test_second_identical_update_is_idempotent() -> None:
    first = update_research_memory_and_build_p3_handoff(
        normalized=normalized(),
        previous_snapshot=None,
        policy=ResearchMemoryUpdatePolicy(policy_id="memory"),
        current_cycle=SOURCE_CYCLE,
        created_at=NOW,
    )
    assert first.output is not None
    second = update_research_memory_and_build_p3_handoff(
        normalized=normalized(),
        previous_snapshot=first.output.memory_update.memory_snapshot,
        policy=ResearchMemoryUpdatePolicy(policy_id="memory"),
        current_cycle=SOURCE_CYCLE,
        created_at=NOW,
    )
    assert second.output is not None
    assert not second.output.memory_update.added_item_ids
    assert second.output.memory_update.unchanged_item_ids


def test_active_item_limit_fails_closed() -> None:
    result = update_research_memory_and_build_p3_handoff(
        normalized=normalized(),
        previous_snapshot=None,
        policy=ResearchMemoryUpdatePolicy(policy_id="memory", maximum_active_items=1),
        current_cycle=SOURCE_CYCLE,
        created_at=NOW,
    )
    assert result.status == ModuleStatus.INVALID
    assert result.output is None


def test_forbidden_text_fragment_is_blocked() -> None:
    candidate = research_candidates()[0].model_copy(
        update={
            "candidate_id": "text-blocked",
            "semantic_key": "text-blocked-key",
            "abstract_claim": "The private leaderboard reveals a future relationship.",
        }
    )
    result = update_research_memory_and_build_p3_handoff(
        normalized=normalized((candidate,)),
        previous_snapshot=None,
        policy=ResearchMemoryUpdatePolicy(policy_id="memory"),
        current_cycle=SOURCE_CYCLE,
        created_at=NOW,
    )
    assert result.output is not None
    assert result.output.p3_handoff.state == P3ContextState.TEMPORAL_LEAKAGE_BLOCKED
