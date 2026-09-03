from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    EvidenceQuality,
    ModuleStatus,
)

from .enums import (
    MemoryUpdateState,
    P3ContextCategory,
    P3ContextState,
    ResearchItemState,
    ResearchItemType,
)
from .hashing import sha256_hex
from .models import (
    CycleRef,
    MemoryAndP3HandoffOutput,
    ModuleDiagnostics,
    NormalizedResearchMemoryBundle,
    P3ContextHandoffManifest,
    P3ResearchContextHandoff,
    P3ResearchContextItem,
    ResearchMemoryItem,
    ResearchMemorySnapshot,
    ResearchMemoryUpdatePolicy,
    SystemResearchMemoryUpdate,
    build_module_result,
)

MODULE_ID = "P9.S10.M02"
_EXPORTABLE_TYPES = {
    ResearchItemType.SUPPORTED_LESSON,
    ResearchItemType.CONDITIONAL_LESSON,
    ResearchItemType.PLAUSIBLE_HYPOTHESIS,
    ResearchItemType.UNRESOLVED_QUESTION,
    ResearchItemType.NEGATIVE_MEMORY,
    ResearchItemType.BREAKPOINT_MEMORY,
}
_QUALITY_RANK = {
    EvidenceQuality.UNAVAILABLE: 0,
    EvidenceQuality.CENSORED: 1,
    EvidenceQuality.MODEL_BASED_COUNTERFACTUAL: 2,
    EvidenceQuality.OBSERVABLE_COUNTERFACTUAL: 3,
    EvidenceQuality.FACTUAL_OBSERVED: 4,
    EvidenceQuality.FACTUAL_EXECUTED: 5,
}


def _build_snapshot(
    *,
    memory_id: str,
    generation: int,
    previous_snapshot_sha256: str | None,
    items: tuple[ResearchMemoryItem, ...],
) -> ResearchMemorySnapshot:
    ordered = tuple(sorted(items, key=lambda item: item.item_id))
    payload = {
        "memory_id": memory_id,
        "generation": generation,
        "previous_snapshot_sha256": previous_snapshot_sha256,
        "items": ordered,
    }
    return ResearchMemorySnapshot(
        memory_id=memory_id,
        generation=generation,
        previous_snapshot_sha256=previous_snapshot_sha256,
        items=ordered,
        snapshot_sha256=sha256_hex(payload),
    )


def _category(item: ResearchMemoryItem) -> P3ContextCategory:
    if item.item_type in {ResearchItemType.NEGATIVE_MEMORY, ResearchItemType.BREAKPOINT_MEMORY}:
        return P3ContextCategory.FAILURE_PATTERN
    if item.item_type in {
        ResearchItemType.PLAUSIBLE_HYPOTHESIS,
        ResearchItemType.REJECTED_HYPOTHESIS,
    }:
        return P3ContextCategory.RESEARCH_HYPOTHESIS
    if item.item_type == ResearchItemType.UNRESOLVED_QUESTION:
        return P3ContextCategory.RESEARCH_QUESTION
    if item.evidence_against:
        return P3ContextCategory.UNCERTAINTY
    return P3ContextCategory.ABSTRACT_LESSON


def _quality(item: ResearchMemoryItem) -> EvidenceQuality:
    values = tuple(reference.quality for reference in item.evidence_for + item.evidence_against)
    if not values:
        return EvidenceQuality.UNAVAILABLE
    return min(values, key=lambda value: _QUALITY_RANK[value])


def _uncertainty(item: ResearchMemoryItem) -> str:
    if item.evidence_against:
        return (
            f"Confidence {item.confidence:.3f}; contrary evidence remains and the claim is "
            "valid only inside the declared scope."
        )
    return (
        f"Confidence {item.confidence:.3f}; interpretation remains bounded by the declared "
        "scope, regimes, and evidence quality."
    )


def _question(item: ResearchMemoryItem) -> str:
    if item.item_type in {ResearchItemType.NEGATIVE_MEMORY, ResearchItemType.BREAKPOINT_MEMORY}:
        return "Under which observable conditions does this failure pattern reappear?"
    if item.item_type == ResearchItemType.REJECTED_HYPOTHESIS:
        return "Which new evidence would justify reopening this rejected hypothesis?"
    if item.item_type == ResearchItemType.UNRESOLVED_QUESTION:
        return "What additional evidence can resolve this open research question?"
    return "Can this abstract relationship be reproduced in a future, leakage-safe cycle?"


def _text_is_forbidden(item: ResearchMemoryItem, policy: ResearchMemoryUpdatePolicy) -> bool:
    text = f"{item.claim} {item.abstract_claim}".casefold()
    return any(fragment.casefold() in text for fragment in policy.forbidden_text_fragments)


def update_research_memory_and_build_p3_handoff(
    *,
    normalized: NormalizedResearchMemoryBundle,
    previous_snapshot: ResearchMemorySnapshot | None,
    policy: ResearchMemoryUpdatePolicy,
    current_cycle: CycleRef,
    created_at: datetime,
):
    incoming = (
        normalized.matured_lessons.items
        + normalized.research_hypotheses.items
        + normalized.negative_memory.items
    )
    if previous_snapshot is None:
        previous_snapshot = _build_snapshot(
            memory_id="p9-system-research-memory",
            generation=0,
            previous_snapshot_sha256=None,
            items=(),
        )

    existing_by_id = {item.item_id: item for item in previous_snapshot.items}
    existing_by_key = {item.semantic_key: item for item in previous_snapshot.items}
    updated = dict(existing_by_id)
    added_ids: list[str] = []
    superseded_ids: set[str] = set()
    unchanged_ids: list[str] = []

    for item in incoming:
        if item.item_id in existing_by_id:
            unchanged_ids.append(item.item_id)
            continue
        explicit_supersedes = set(item.supersedes_item_ids)
        same_key = existing_by_key.get(item.semantic_key)
        if same_key is not None and same_key.item_type not in {
            ResearchItemType.NEGATIVE_MEMORY,
            ResearchItemType.BREAKPOINT_MEMORY,
        }:
            explicit_supersedes.add(same_key.item_id)
        for old_id in explicit_supersedes:
            old = updated.get(old_id)
            if old is not None and old.state == ResearchItemState.ACTIVE:
                updated[old_id] = old.model_copy(update={"state": ResearchItemState.SUPERSEDED})
                superseded_ids.add(old_id)
        for old_id in item.contradicts_item_ids:
            old = updated.get(old_id)
            if old is not None and old.state == ResearchItemState.ACTIVE:
                updated[old_id] = old.model_copy(update={"state": ResearchItemState.CONTRADICTED})
        updated[item.item_id] = item
        added_ids.append(item.item_id)

    for item_id, item in tuple(updated.items()):
        expires = item.expires_after_cycle
        if expires is not None and current_cycle.ordinal > expires.ordinal:
            if item.state == ResearchItemState.ACTIVE:
                updated[item_id] = item.model_copy(update={"state": ResearchItemState.EXPIRED})

    active_count = sum(item.state == ResearchItemState.ACTIVE for item in updated.values())
    if active_count > policy.maximum_active_items:
        return build_module_result(
            module_id=MODULE_ID,
            status=ModuleStatus.INVALID,
            output=None,
            diagnostics=ModuleDiagnostics(
                counters=(("active_item_count", active_count),),
                trace=("maximum active research memory items exceeded",),
            ),
            reason_codes=("P9_MEMORY_ACTIVE_ITEM_LIMIT_EXCEEDED",),
        )

    new_snapshot = _build_snapshot(
        memory_id=previous_snapshot.memory_id,
        generation=previous_snapshot.generation + 1,
        previous_snapshot_sha256=previous_snapshot.snapshot_sha256,
        items=tuple(updated.values()),
    )
    update_state = (
        MemoryUpdateState.RESEARCH_MEMORY_UPDATED
        if added_ids or superseded_ids
        else MemoryUpdateState.RESEARCH_MEMORY_UNCHANGED
    )
    memory_update = SystemResearchMemoryUpdate(
        state=update_state,
        previous_snapshot_sha256=previous_snapshot.snapshot_sha256,
        memory_snapshot=new_snapshot,
        added_item_ids=tuple(sorted(added_ids)),
        superseded_item_ids=tuple(sorted(superseded_ids)),
        unchanged_item_ids=tuple(sorted(unchanged_ids)),
    )

    blocked_ids: list[str] = []
    context_items: list[P3ResearchContextItem] = []
    for item in sorted(
        new_snapshot.items,
        key=lambda value: (value.materiality, value.confidence, value.item_id),
        reverse=True,
    ):
        if item.state != ResearchItemState.ACTIVE or item.item_type not in _EXPORTABLE_TYPES:
            continue
        blocked = item.export_blocked or _text_is_forbidden(item, policy)
        if blocked:
            blocked_ids.append(item.item_id)
            continue
        digest = sha256_hex(
            {
                "memory_item_id": item.item_id,
                "contract_version": policy.p3_schema_version,
            }
        )[:24]
        context_items.append(
            P3ResearchContextItem(
                context_item_id=f"p3-research-context-{digest}",
                category=_category(item),
                abstract_claim=item.abstract_claim,
                uncertainty=_uncertainty(item),
                research_question=_question(item),
                scope=item.scope,
                source_memory_item_id=item.item_id,
                evidence_quality=_quality(item),
            )
        )
        if len(context_items) >= policy.maximum_p3_items:
            break

    if context_items:
        handoff_state = P3ContextState.P3_CONTEXT_READY
        reason_codes: tuple[str, ...] = ()
    elif blocked_ids:
        handoff_state = P3ContextState.TEMPORAL_LEAKAGE_BLOCKED
        reason_codes = ("P9_P3_CONTEXT_TEMPORAL_LEAKAGE_BLOCKED",)
    else:
        handoff_state = P3ContextState.NO_EXPORTABLE_CONTEXT
        reason_codes = ("P9_P3_CONTEXT_EMPTY",)

    handoff = P3ResearchContextHandoff(
        contract_version=policy.p3_schema_version,
        state=handoff_state,
        context_items=tuple(context_items),
        blocked_memory_item_ids=tuple(sorted(blocked_ids)),
        reason_codes=reason_codes,
    )
    handoff_hash = sha256_hex(handoff)
    manifest = P3ContextHandoffManifest(
        manifest_id=f"p3-context-manifest-{handoff_hash[:24]}",
        source_memory_snapshot_sha256=new_snapshot.snapshot_sha256,
        handoff_sha256=handoff_hash,
        contract_name=handoff.contract_name,
        contract_version=handoff.contract_version,
        context_item_ids=tuple(item.context_item_id for item in handoff.context_items),
        blocked_memory_item_ids=handoff.blocked_memory_item_ids,
        created_at=created_at,
    )
    output = MemoryAndP3HandoffOutput(
        memory_update=memory_update,
        p3_handoff=handoff,
        p3_manifest=manifest,
    )
    status = (
        ModuleStatus.LIMITED
        if handoff_state != P3ContextState.P3_CONTEXT_READY
        else ModuleStatus.SUCCESS
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=output,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("incoming_item_count", len(incoming)),
                ("memory_item_count", len(new_snapshot.items)),
                ("p3_context_item_count", len(context_items)),
                ("blocked_item_count", len(blocked_ids)),
            ),
            trace=(
                "system research memory updated separately from P3 research context",
                "world memory writes remained disabled",
            ),
        ),
        reason_codes=reason_codes,
    )
