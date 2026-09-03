from __future__ import annotations

from dataclasses import replace

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus
from quant_pipeline.phase_09.subphases.s10_memory_release import (
    CausalStatus,
    OutcomeMaturity,
    ResearchItemType,
    normalize_matured_research_memory,
)
from quant_pipeline.phase_09.subphases.s10_memory_release.models import (
    ResearchClaimCandidate,
    ResearchNormalizationPolicy,
)

from tests.s10.conftest import SOURCE_CYCLE, evidence, research_candidates


def policy() -> ResearchNormalizationPolicy:
    return ResearchNormalizationPolicy(policy_id="policy")


def test_normalizes_lessons_hypotheses_and_negative_memory() -> None:
    result = normalize_matured_research_memory(candidates=research_candidates(), policy=policy())
    assert result.output is not None
    assert len(result.output.matured_lessons.items) == 1
    assert len(result.output.research_hypotheses.items) == 1
    assert len(result.output.negative_memory.items) == 1
    assert result.status == ModuleStatus.LIMITED
    assert result.output.skipped_candidate_ids == ("claim-immature",)


def test_deduplicates_same_semantic_key() -> None:
    base = research_candidates()[0]
    duplicate = base.model_copy(update={"candidate_id": "claim-supported-2", "confidence": 0.97})
    result = normalize_matured_research_memory(candidates=(base, duplicate), policy=policy())
    assert result.output is not None
    assert len(result.output.matured_lessons.items) == 1
    assert set(result.output.merged_candidate_ids) == {base.candidate_id, duplicate.candidate_id}
    assert result.output.matured_lessons.items[0].confidence == 0.97


def test_rejects_hypothesis_with_only_strong_contrary_evidence() -> None:
    base = research_candidates()[1]
    rejected = base.model_copy(
        update={
            "candidate_id": "rejected",
            "semantic_key": "rejected-key",
            "evidence_for": (),
            "confidence": 0.90,
        }
    )
    result = normalize_matured_research_memory(candidates=(rejected,), policy=policy())
    assert result.output is not None
    item = result.output.research_hypotheses.items[0]
    assert item.item_type == ResearchItemType.REJECTED_HYPOTHESIS


def test_association_does_not_become_supported_lesson() -> None:
    base = research_candidates()[0]
    associated = base.model_copy(
        update={
            "candidate_id": "associated",
            "semantic_key": "associated-key",
            "causal_status": CausalStatus.ASSOCIATION,
            "confidence": 0.99,
        }
    )
    result = normalize_matured_research_memory(candidates=(associated,), policy=policy())
    assert result.output is not None
    assert (
        result.output.research_hypotheses.items[0].item_type
        == ResearchItemType.PLAUSIBLE_HYPOTHESIS
    )


def test_marks_export_blocked_claim() -> None:
    base = research_candidates()[0]
    blocked = base.model_copy(
        update={
            "candidate_id": "blocked",
            "semantic_key": "blocked-key",
            "contains_private_leaderboard_data": True,
        }
    )
    result = normalize_matured_research_memory(candidates=(blocked,), policy=policy())
    assert result.output is not None
    item = result.output.matured_lessons.items[0]
    assert item.export_blocked
    assert "P9_MEMORY_PRIVATE_LEADERBOARD_DATA" in item.export_block_reasons


def test_supersession_cycle_is_invalid() -> None:
    first = research_candidates()[0].model_copy(
        update={
            "candidate_id": "first",
            "semantic_key": "first-key",
            "supersedes_semantic_keys": ("second-key",),
        }
    )
    second = research_candidates()[2].model_copy(
        update={
            "candidate_id": "second",
            "semantic_key": "second-key",
            "supersedes_semantic_keys": ("first-key",),
        }
    )
    result = normalize_matured_research_memory(candidates=(first, second), policy=policy())
    assert result.status == ModuleStatus.INVALID
    assert result.output is None
    assert "P9_MEMORY_SUPERSESSION_CYCLE" in result.reason_codes


def test_order_does_not_change_hash() -> None:
    candidates = research_candidates()[:3]
    first = normalize_matured_research_memory(candidates=candidates, policy=policy())
    second = normalize_matured_research_memory(
        candidates=tuple(reversed(candidates)), policy=policy()
    )
    assert first.output_sha256 == second.output_sha256
