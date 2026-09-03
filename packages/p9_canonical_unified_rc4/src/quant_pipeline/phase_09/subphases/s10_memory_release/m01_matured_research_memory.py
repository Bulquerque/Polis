from __future__ import annotations

from collections import defaultdict

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import ModuleStatus

from .enums import CausalStatus, OutcomeMaturity, ResearchItemState, ResearchItemType
from .hashing import sha256_hex
from .models import (
    MaturedLessonPanel,
    ModuleDiagnostics,
    NegativeResearchMemoryPanel,
    NormalizedResearchMemoryBundle,
    ResearchClaimCandidate,
    ResearchHypothesisPanel,
    ResearchMemoryItem,
    ResearchNormalizationPolicy,
    build_module_result,
)

MODULE_ID = "P9.S10.M01"
_MATURE_STATES = {OutcomeMaturity.MATURED, OutcomeMaturity.SETTLED}
_NEGATIVE_TYPES = {ResearchItemType.NEGATIVE_MEMORY, ResearchItemType.BREAKPOINT_MEMORY}
_LESSON_TYPES = {ResearchItemType.SUPPORTED_LESSON, ResearchItemType.CONDITIONAL_LESSON}
_HYPOTHESIS_TYPES = {
    ResearchItemType.PLAUSIBLE_HYPOTHESIS,
    ResearchItemType.REJECTED_HYPOTHESIS,
    ResearchItemType.UNRESOLVED_QUESTION,
}


def _unique_evidence(values):
    by_id = {value.evidence_id: value for value in values}
    return tuple(sorted(by_id.values(), key=lambda value: value.evidence_id))


def _classify(candidate: ResearchClaimCandidate, policy: ResearchNormalizationPolicy):
    if candidate.item_type_hint in _NEGATIVE_TYPES:
        return candidate.item_type_hint
    if candidate.item_type_hint == ResearchItemType.REJECTED_HYPOTHESIS:
        return ResearchItemType.REJECTED_HYPOTHESIS
    has_support = bool(candidate.evidence_for)
    has_contrary = bool(candidate.evidence_against)
    is_attributed = candidate.causal_status in {CausalStatus.ATTRIBUTED, CausalStatus.CAUSAL}
    material = candidate.materiality >= policy.minimum_materiality
    if is_attributed and material and candidate.confidence >= policy.supported_lesson_confidence:
        if not has_contrary:
            return ResearchItemType.SUPPORTED_LESSON
        return ResearchItemType.CONDITIONAL_LESSON
    if is_attributed and material and candidate.confidence >= policy.conditional_lesson_confidence:
        return ResearchItemType.CONDITIONAL_LESSON
    if has_contrary and not has_support:
        if candidate.confidence >= policy.rejected_hypothesis_confidence:
            return ResearchItemType.REJECTED_HYPOTHESIS
    if candidate.confidence >= policy.plausible_hypothesis_confidence:
        return ResearchItemType.PLAUSIBLE_HYPOTHESIS
    return ResearchItemType.UNRESOLVED_QUESTION


def _blocked_reasons(candidates: tuple[ResearchClaimCandidate, ...]) -> tuple[str, ...]:
    reasons: set[str] = set()
    for candidate in candidates:
        if candidate.contains_future_outcome_identifiers:
            reasons.add("P9_MEMORY_FUTURE_OUTCOME_IDENTIFIER")
        if candidate.contains_private_leaderboard_data:
            reasons.add("P9_MEMORY_PRIVATE_LEADERBOARD_DATA")
        if candidate.contains_promoted_parameters:
            reasons.add("P9_MEMORY_PROMOTED_PARAMETER")
        if candidate.contains_direct_patch_instruction:
            reasons.add("P9_MEMORY_DIRECT_PATCH_INSTRUCTION")
        if candidate.contains_asset_specific_future_return:
            reasons.add("P9_MEMORY_ASSET_SPECIFIC_FUTURE_RETURN")
    return tuple(sorted(reasons))


def _detect_supersession_cycle(items: tuple[ResearchMemoryItem, ...]) -> bool:
    graph = {item.item_id: set(item.supersedes_item_ids) for item in items}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in graph.get(node, set()):
            if child in graph and visit(child):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def normalize_matured_research_memory(
    *,
    candidates: tuple[ResearchClaimCandidate, ...],
    policy: ResearchNormalizationPolicy,
):
    matured = tuple(
        candidate for candidate in candidates if candidate.outcome_maturity in _MATURE_STATES
    )
    skipped = tuple(
        sorted(candidate.candidate_id for candidate in candidates if candidate not in matured)
    )
    grouped: dict[str, list[ResearchClaimCandidate]] = defaultdict(list)
    for candidate in matured:
        grouped[candidate.semantic_key].append(candidate)

    item_id_by_key: dict[str, str] = {}
    representative_by_key: dict[str, ResearchClaimCandidate] = {}
    type_by_key: dict[str, ResearchItemType] = {}
    for semantic_key, values in grouped.items():
        ordered = sorted(
            values,
            key=lambda item: (
                item.confidence,
                item.materiality,
                item.validity_start.ordinal,
                item.candidate_id,
            ),
            reverse=True,
        )
        representative = ordered[0]
        item_type = _classify(representative, policy)
        digest = sha256_hex(
            {
                "semantic_key": semantic_key,
                "item_type": item_type,
                "validity_start": representative.validity_start,
            }
        )[:24]
        item_id_by_key[semantic_key] = f"research-memory-{digest}"
        representative_by_key[semantic_key] = representative
        type_by_key[semantic_key] = item_type

    warnings: list[str] = []
    items: list[ResearchMemoryItem] = []
    merged_ids: list[str] = []
    for semantic_key, values in sorted(grouped.items()):
        representative = representative_by_key[semantic_key]
        evidence_for = _unique_evidence(
            tuple(evidence for candidate in values for evidence in candidate.evidence_for)
        )
        evidence_against = _unique_evidence(
            tuple(evidence for candidate in values for evidence in candidate.evidence_against)
        )
        source_cycles = tuple(
            sorted(
                {cycle for candidate in values for cycle in candidate.source_cycles},
                key=lambda cycle: (cycle.ordinal, cycle.cycle_id),
            )
        )
        supersedes_keys = {
            key for candidate in values for key in candidate.supersedes_semantic_keys
        }
        contradicts_keys = {
            key for candidate in values for key in candidate.contradicts_semantic_keys
        }
        unknown = (supersedes_keys | contradicts_keys) - set(item_id_by_key)
        if unknown:
            warnings.append(
                f"{semantic_key}: unresolved relation targets {sorted(unknown)}"
            )
        if len(values) > 1:
            merged_ids.extend(candidate.candidate_id for candidate in values)
        block_reasons = _blocked_reasons(tuple(values))
        item = ResearchMemoryItem(
            item_id=item_id_by_key[semantic_key],
            semantic_key=semantic_key,
            item_type=type_by_key[semantic_key],
            state=ResearchItemState.ACTIVE,
            claim=representative.claim,
            abstract_claim=representative.abstract_claim,
            scope=representative.scope,
            causal_status=representative.causal_status,
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            confidence=max(candidate.confidence for candidate in values),
            materiality=max(candidate.materiality for candidate in values),
            validity_start=max(
                (candidate.validity_start for candidate in values),
                key=lambda cycle: cycle.ordinal,
            ),
            expires_after_cycle=representative.expires_after_cycle,
            source_cycles=source_cycles,
            supersedes_item_ids=tuple(
                sorted(item_id_by_key[key] for key in supersedes_keys if key in item_id_by_key)
            ),
            contradicts_item_ids=tuple(
                sorted(item_id_by_key[key] for key in contradicts_keys if key in item_id_by_key)
            ),
            export_blocked=bool(block_reasons),
            export_block_reasons=block_reasons,
        )
        items.append(item)

    materialized = tuple(items)
    if _detect_supersession_cycle(materialized):
        return build_module_result(
            module_id=MODULE_ID,
            status=ModuleStatus.INVALID,
            output=None,
            diagnostics=ModuleDiagnostics(trace=("supersession cycle detected",)),
            reason_codes=("P9_MEMORY_SUPERSESSION_CYCLE",),
        )

    output = NormalizedResearchMemoryBundle(
        policy_id=policy.policy_id,
        matured_lessons=MaturedLessonPanel(
            items=tuple(item for item in materialized if item.item_type in _LESSON_TYPES)
        ),
        research_hypotheses=ResearchHypothesisPanel(
            items=tuple(item for item in materialized if item.item_type in _HYPOTHESIS_TYPES)
        ),
        negative_memory=NegativeResearchMemoryPanel(
            items=tuple(item for item in materialized if item.item_type in _NEGATIVE_TYPES)
        ),
        skipped_candidate_ids=skipped,
        merged_candidate_ids=tuple(sorted(set(merged_ids))),
        warnings=tuple(sorted(set(warnings))),
    )
    status = ModuleStatus.LIMITED if skipped or warnings else ModuleStatus.SUCCESS
    reason_codes = ("P9_MEMORY_IMMATURE_CLAIMS_SKIPPED",) if skipped else ()
    evidence_refs = _unique_evidence(
        tuple(
            evidence
            for item in materialized
            for evidence in item.evidence_for + item.evidence_against
        )
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=output,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("candidate_count", len(candidates)),
                ("matured_count", len(matured)),
                ("memory_item_count", len(materialized)),
                ("skipped_count", len(skipped)),
            ),
            warnings=tuple(output.warnings),
        ),
        evidence_refs=evidence_refs,
        reason_codes=reason_codes,
    )
