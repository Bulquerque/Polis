from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

from .errors import S20BudgetError, S20LineageError, S20TemporalError
from .hashing import sha256_value, stable_id
from ..governance.live_safety import render_untrusted_text
from .models import (
    ActivationPanel,
    Belief,
    BeliefPanel,
    BudgetConfig,
    BudgetReport,
    CognitiveSchedule,
    ContextBundle,
    ContextLearningConfig,
    ContextSection,
    CutoffReport,
    CutoffRisk,
    Entitlement,
    EntitlementPanel,
    EvidenceMap,
    EvidenceMapEntry,
    ExperienceStatus,
    GraphArtifact,
    GraphConfig,
    IndexedItem,
    PersonContext,
    PersonState,
    PersonStatePanel,
    QueryPanel,
    ScheduleStep,
    RetrievalBundle,
    RetrievalConfig,
    RetrievalQuery,
    RetrievalStatus,
    RetrievedEvidence,
    RetroPatch,
    RunSnapshot,
    SocialEdge,
    SocialGraph,
    SourceType,
    Status,
    Stimulus,
    StimulusPanel,
    TriggerType,
    ValidatedContext,
    ValidatedContextBundle,
)
from .ports import KnowledgePort, MemoryPort, RerankerPort, TokenizerPort


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9_]+", text.lower()))


def _overlap(query: str, text: str) -> float:
    query_tokens = _tokens(query)
    text_tokens = _tokens(text)
    if not query_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def _recency(event_time: datetime | None, as_of: datetime) -> float:
    if event_time is None:
        return 0.5
    days = max(0.0, (as_of - event_time).total_seconds() / 86_400)
    return 1.0 / (1.0 + days / 30.0)



def _query_for_step(
    *,
    step: ScheduleStep,
    person: PersonState,
    stimulus: Stimulus | None,
    beliefs: tuple[Belief, ...],
    schedule: CognitiveSchedule,
    snapshot: RunSnapshot,
) -> RetrievalQuery:
    topic = stimulus.subject if stimulus is not None else (
        f"monthly heartbeat for role {person.role} objective {person.objective}"
    )
    anchors = "; ".join(
        f"{belief.proposition_id}:{belief.value:.3f}/{belief.confidence:.3f}"
        for belief in sorted(beliefs, key=lambda item: (item.proposition_id, item.horizon))
    )
    query_text = (
        f"{topic}. Role={person.role}. Objective={person.objective}. "
        f"Attention={person.current_attention:.3f}. Prior beliefs={anchors or 'none'}."
    )
    lineage = tuple(dict.fromkeys(
        step.source_lineage_ids + (stimulus.lineage_ids if stimulus is not None else ())
    ))
    return RetrievalQuery(
        query_id=stable_id("query", snapshot.run_id, snapshot.cycle_id, step.schedule_step_id, step.person_id),
        schedule_step_id=step.schedule_step_id,
        person_id=step.person_id,
        trigger_type=step.trigger_type,
        activation_id=step.activation_id,
        stimulus_id=step.stimulus_id,
        query_text=query_text,
        underlying_id=stimulus.selected_underlying_id if stimulus is not None else None,
        proposition_id=stimulus.proposition_id if stimulus is not None else None,
        horizon=stimulus.horizon if stimulus is not None else None,
        as_of=schedule.as_of,
        memory_scope="PERSON_ONLY",
        knowledge_scope="PIT_AUTHORIZED",
        source_lineage_ids=lineage,
    )


def _resolve_query_inputs(
    *,
    step: ScheduleStep,
    persons: dict[str, PersonState],
    stimuli: dict[str, Stimulus],
    activations: dict[str, object],
    beliefs: BeliefPanel,
    snapshot: RunSnapshot,
) -> tuple[PersonState, Stimulus | None, tuple[Belief, ...]]:
    person = persons.get(step.person_id)
    if person is None or not person.enabled:
        raise ValueError(f"missing/enabled person {step.person_id}")
    if person.available_at > snapshot.as_of:
        raise S20TemporalError("future person state")
    stimulus = stimuli.get(step.stimulus_id) if step.stimulus_id else None
    activation = activations.get(step.activation_id) if step.activation_id else None
    if step.trigger_type == TriggerType.STIMULUS and (activation is None or stimulus is None):
        raise ValueError("stimulus schedule missing activation/stimulus")
    if stimulus is not None and (stimulus.available_at > snapshot.as_of or stimulus.event_time > snapshot.as_of):
        raise S20TemporalError("future stimulus in context preparation")
    prior = tuple(
        belief for belief in beliefs.records
        if belief.person_id == step.person_id and belief.available_at <= snapshot.as_of
    )
    return person, stimulus, prior


def build_queries(
    schedule: CognitiveSchedule,
    stimuli: StimulusPanel,
    activations: ActivationPanel,
    states: PersonStatePanel,
    beliefs: BeliefPanel,
    snapshot: RunSnapshot,
) -> QueryPanel:
    """Build one deterministic retrieval query for each cognitive schedule step."""
    if schedule.run_id != snapshot.run_id or schedule.cycle_id != snapshot.cycle_id:
        raise ValueError("identity mismatch")
    stimulus_by_id = {record.stimulus_id: record for record in stimuli.records}
    activation_by_id = {record.activation_id: record for record in activations.records}
    person_by_id = {record.person_id: record for record in states.records}
    queries: list[RetrievalQuery] = []
    for step in schedule.records:
        person, stimulus, prior = _resolve_query_inputs(
            step=step, persons=person_by_id, stimuli=stimulus_by_id,
            activations=activation_by_id, beliefs=beliefs, snapshot=snapshot,
        )
        queries.append(_query_for_step(
            step=step, person=person, stimulus=stimulus, beliefs=prior,
            schedule=schedule, snapshot=snapshot,
        ))
    payload = {"records": [q.model_dump(mode="json") for q in queries], "run_id": snapshot.run_id, "cycle_id": snapshot.cycle_id}
    return QueryPanel(
        schema_version="person_retrieval_query_panel.v1", run_id=snapshot.run_id,
        cycle_id=snapshot.cycle_id, as_of=schedule.as_of, records=tuple(queries),
        content_hash=sha256_value(payload), status=Status.READY if queries else Status.READY_EMPTY,
    )


@dataclass(frozen=True)
class InMemoryPort(MemoryPort, KnowledgePort):
    """Deterministic in-memory retrieval adapter used by tests and local runs."""

    items: tuple[IndexedItem, ...]
    person_isolated: bool

    def search(
        self,
        query: RetrievalQuery,
        *,
        top_k: int,
    ) -> tuple[IndexedItem, ...]:
        candidates: list[tuple[float, float, float, str, IndexedItem]] = []
        for item in self.items:
            if item.available_at > query.as_of:
                continue
            if self.person_isolated and item.person_id != query.person_id:
                continue
            if not self.person_isolated and item.person_id not in (
                None,
                query.person_id,
            ):
                continue
            score = max(
                item.semantic_score,
                _overlap(query.query_text, item.text),
            )
            candidates.append(
                (
                    score,
                    item.importance,
                    item.source_quality,
                    item.item_id,
                    item,
                )
            )
        candidates.sort(
            key=lambda row: (-row[0], -row[1], -row[2], row[3])
        )
        return tuple(row[-1] for row in candidates[:top_k])


def _convert(
    query: RetrievalQuery,
    item: IndexedItem,
    source: SourceType,
    rank: int,
) -> RetrievedEvidence:
    if item.available_at > query.as_of:
        raise S20TemporalError("future retrieval item")
    overlap = _overlap(query.query_text, item.text)
    return RetrievedEvidence(
        query_text=query.query_text,
        evidence_id=stable_id(
            "evidence",
            query.query_id,
            source,
            item.item_id,
        ),
        query_id=query.query_id,
        person_id=query.person_id,
        source_type=source,
        source_id=item.item_id,
        text=item.text,
        available_at=item.available_at,
        event_time=item.event_time,
        content_hash=item.content_hash,
        semantic_score=max(item.semantic_score, overlap),
        keyword_score=max(item.keyword_score, overlap),
        recency_score=_recency(item.event_time, query.as_of),
        importance_score=item.importance,
        source_quality_score=item.source_quality,
        rank_before=rank,
        evidence_refs=item.evidence_refs,
        lineage_ids=(item.lineage_id,),
        experience_status=item.experience_status,
        commitment_id=item.commitment_id,
    )


def retrieve_hybrid(
    queries: QueryPanel,
    memory: MemoryPort,
    knowledge: KnowledgePort,
    config: RetrievalConfig,
) -> RetrievalBundle:
    """Retrieve person-isolated memory and PIT-authorized documents."""
    evidence: list[RetrievedEvidence] = []
    warnings: list[str] = []
    for query in queries.records:
        memories = memory.search(query, top_k=config.memory_top_k)
        documents = knowledge.search(query, top_k=config.document_top_k)
        evidence.extend(
            _convert(query, item, SourceType.MEMORY, index + 1)
            for index, item in enumerate(memories)
        )
        evidence.extend(
            _convert(query, item, SourceType.DOCUMENT, index + 1)
            for index, item in enumerate(documents)
        )

    status = (
        RetrievalStatus.READY if evidence else RetrievalStatus.READY_EMPTY
    )
    payload = [record.model_dump(mode="json") for record in evidence]
    return RetrievalBundle(
        schema_version="raw_retrieved_knowledge_bundle.v1",
        run_id=queries.run_id,
        cycle_id=queries.cycle_id,
        as_of=queries.as_of,
        records=tuple(evidence),
        content_hash=sha256_value(payload),
        status=status,
        warnings=tuple(warnings),
    )


def retrieve_graph(
    queries: QueryPanel,
    graph: GraphArtifact,
    config: GraphConfig,
    top_k: int,
) -> RetrievalBundle:
    """Traverse a portable temporal evidence graph with bounded depth."""
    adjacency: dict[str, list] = defaultdict(list)
    for edge in graph.edges:
        if config.edge_requires_evidence and not edge.evidence_refs:
            raise S20LineageError("graph edge without evidence")
        adjacency[edge.source_node_id].append(edge)
        adjacency[edge.target_node_id].append(edge)

    evidence: list[RetrievedEvidence] = []
    for query in queries.records:
        starts = [
            node_id
            for node_id in (query.underlying_id, query.proposition_id)
            if node_id
        ]
        seen = set(starts)
        queue = deque((node_id, 0) for node_id in starts)
        query_evidence: list[RetrievedEvidence] = []
        rank = 1
        max_visits = (
            config.max_query_hops * config.max_query_hops
            + config.max_query_hops
        )

        while queue and rank <= max_visits:
            node_id, depth = queue.popleft()
            if depth >= config.max_query_hops:
                continue
            for edge in sorted(
                adjacency.get(node_id, ()),
                key=lambda candidate: candidate.edge_id,
            ):
                if edge.available_at > query.as_of:
                    continue
                next_node = (
                    edge.target_node_id
                    if edge.source_node_id == node_id
                    else edge.source_node_id
                )
                evidence_id = stable_id(
                    "evidence",
                    query.query_id,
                    "GRAPH",
                    edge.edge_id,
                )
                overlap = _overlap(query.query_text, edge.text)
                query_evidence.append(
                    RetrievedEvidence(
                        query_text=query.query_text,
                        evidence_id=evidence_id,
                        query_id=query.query_id,
                        person_id=query.person_id,
                        source_type=SourceType.GRAPH,
                        source_id=edge.edge_id,
                        text=edge.text,
                        available_at=edge.available_at,
                        content_hash=sha256_value(
                            edge.model_dump(mode="json")
                        ),
                        semantic_score=overlap,
                        keyword_score=overlap,
                        recency_score=_recency(None, query.as_of),
                        importance_score=edge.weight,
                        source_quality_score=1.0,
                        rank_before=rank,
                        evidence_refs=edge.evidence_refs,
                        lineage_ids=(edge.lineage_id,),
                    )
                )
                rank += 1
                if next_node not in seen:
                    seen.add(next_node)
                    queue.append((next_node, depth + 1))
        evidence.extend(query_evidence[:top_k])

    return RetrievalBundle(
        schema_version="graph_retrieval_bundle.v1",
        run_id=queries.run_id,
        cycle_id=queries.cycle_id,
        as_of=queries.as_of,
        records=tuple(evidence),
        content_hash=sha256_value(
            [record.model_dump(mode="json") for record in evidence]
        ),
        status=(
            RetrievalStatus.READY
            if evidence
            else RetrievalStatus.READY_EMPTY
        ),
    )


def retrieve_experiences(
    queries: QueryPanel,
    memory_items: tuple[IndexedItem, ...],
    config: RetrievalConfig,
    learning: ContextLearningConfig,
) -> RetrievalBundle:
    """Retrieve matured, person-scoped experiences from current memory."""
    evidence: list[RetrievedEvidence] = []
    allowed = {
        ExperienceStatus.SUCCESSFUL,
        ExperienceStatus.FAILED,
        ExperienceStatus.MATURED_NEUTRAL,
    }
    if learning.include_immature:
        allowed.add(ExperienceStatus.IMMATURE)

    for query in queries.records:
        candidates = [
            item
            for item in memory_items
            if item.person_id == query.person_id
            and item.available_at <= query.as_of
            and item.experience_status in allowed
        ]
        candidates.sort(
            key=lambda item: (
                -_overlap(query.query_text, item.text),
                -item.importance,
                item.item_id,
            )
        )
        evidence.extend(
            _convert(query, item, SourceType.EXPERIENCE, index + 1)
            for index, item in enumerate(
                candidates[: config.experience_top_k]
            )
        )

    return RetrievalBundle(
        schema_version="person_learning_trajectory_bundle.v1",
        run_id=queries.run_id,
        cycle_id=queries.cycle_id,
        as_of=queries.as_of,
        records=tuple(evidence),
        content_hash=sha256_value(
            [record.model_dump(mode="json") for record in evidence]
        ),
        status=(
            RetrievalStatus.READY
            if evidence
            else RetrievalStatus.READY_EMPTY
        ),
    )


def _weighted_score(record: RetrievedEvidence, config: RetrievalConfig) -> float:
    return (
        config.semantic_weight * (record.semantic_score or 0.0)
        + config.keyword_weight * (record.keyword_score or 0.0)
        + config.recency_weight * (record.recency_score or 0.0)
        + config.importance_weight * (record.importance_score or 0.0)
        + config.source_quality_weight
        * (record.source_quality_score or 0.0)
    )



def _rerank_query_records(
    query_id: str,
    records: list[RetrievedEvidence],
    config: RetrievalConfig,
    reranker: RerankerPort | None,
) -> tuple[list[RetrievedEvidence], str | None]:
    query_text = records[0].query_text
    if any(record.query_text != query_text for record in records):
        raise ValueError(f"query text mismatch for {query_id}")
    external = reranker.rank(query_text, tuple(record.text for record in records)) if reranker is not None and records else ()
    scored = [
        (
            float(external[index]) if external else _weighted_score(record, config),
            record.source_id,
            record,
        )
        for index, record in enumerate(records)
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    counts: Counter[SourceType] = Counter()
    final: list[RetrievedEvidence] = []
    for score, _, record in scored:
        if counts[record.source_type] >= config.max_items_per_source:
            continue
        counts[record.source_type] += 1
        final.append(record.model_copy(update={"reranker_score": score, "rank_after": len(final) + 1}))
        if len(final) >= config.final_top_k:
            break
    warning = f"{query_id}:INSUFFICIENT_EVIDENCE" if len(final) < config.minimum_evidence_items else None
    return final, warning


def _retrieval_outputs(
    *, run_id: str, cycle_id: str, as_of: datetime,
    selected: list[RetrievedEvidence], warnings: list[str], reranker: RerankerPort | None,
) -> tuple[RetrievalBundle, EvidenceMap]:
    status = RetrievalStatus.DEGRADED if warnings else RetrievalStatus.READY if selected else RetrievalStatus.READY_EMPTY
    bundle = RetrievalBundle(
        schema_version="retrieved_knowledge_bundle.v1", run_id=run_id, cycle_id=cycle_id,
        as_of=as_of, records=tuple(selected),
        content_hash=sha256_value([r.model_dump(mode="json") for r in selected]),
        status=status, warnings=tuple(warnings),
        ranking_policy_id="external_reranker_v1" if reranker is not None else "weighted_fusion_v1",
        ranking_provider_ref=getattr(reranker, "ref", type(reranker).__name__) if reranker is not None else "internal_weighted_fusion",
        score_semantics="provider_normalized_score" if reranker is not None else "weighted_unit_interval",
    )
    entries = tuple(EvidenceMapEntry(
        evidence_id=r.evidence_id, query_id=r.query_id, source_type=r.source_type,
        source_id=r.source_id, content_hash=r.content_hash, available_at=r.available_at,
        evidence_refs=r.evidence_refs, lineage_ids=r.lineage_ids,
    ) for r in selected)
    return bundle, EvidenceMap(
        schema_version="retrieval_evidence_map.v1", run_id=run_id, cycle_id=cycle_id,
        records=entries, content_hash=sha256_value([e.model_dump(mode="json") for e in entries]), status=status,
    )


def rerank(
    bundles: tuple[RetrievalBundle, ...],
    config: RetrievalConfig,
    reranker: RerankerPort | None = None,
) -> tuple[RetrievalBundle, EvidenceMap]:
    """Fuse retrieval families and build the authoritative evidence map."""
    if not bundles:
        raise ValueError("at least one retrieval bundle is required")
    identity = (bundles[0].run_id, bundles[0].cycle_id, bundles[0].as_of)
    if any((b.run_id, b.cycle_id, b.as_of) != identity for b in bundles):
        raise ValueError("retrieval bundle identity mismatch")
    by_query: dict[str, list[RetrievedEvidence]] = defaultdict(list)
    for bundle in bundles:
        for record in bundle.records:
            by_query[record.query_id].append(record)
    selected: list[RetrievedEvidence] = []
    warnings: list[str] = []
    for query_id, records in sorted(by_query.items()):
        chosen, warning = _rerank_query_records(query_id, records, config, reranker)
        selected.extend(chosen)
        if warning:
            warnings.append(warning)
    return _retrieval_outputs(
        run_id=identity[0], cycle_id=identity[1], as_of=identity[2],
        selected=selected, warnings=warnings, reranker=reranker,
    )


def _context_section(
    *,
    step: ScheduleStep,
    section_type: str,
    priority: int,
    mandatory: bool,
    text: str,
    tokenizer: TokenizerPort,
    items: tuple[str, ...] = (),
    references: tuple[str, ...] = (),
) -> ContextSection:
    return ContextSection(
        section_id=stable_id("section", step.schedule_step_id, section_type),
        section_type=section_type,
        priority=priority,
        mandatory=mandatory,
        text=text,
        item_ids=items,
        source_refs=references,
        content_hash=sha256_value(text),
        estimated_tokens=tokenizer.count(text),
    )


def _build_context_sections(
    *,
    step: ScheduleStep,
    person: PersonState,
    stimulus: Stimulus | None,
    beliefs: tuple[Belief, ...],
    evidence: tuple[RetrievedEvidence, ...],
    relationships: tuple[SocialEdge, ...],
    entitlement: Entitlement | None,
    patch: RetroPatch,
    tokenizer: TokenizerPort,
) -> tuple[ContextSection, ...]:
    trigger_text = stimulus.subject if stimulus else f"Monthly heartbeat {step.heartbeat_period}"
    belief_text = "\n".join(
        f"{item.proposition_id}/{item.horizon}: {item.value} confidence={item.confidence}"
        for item in beliefs
    ) or "none"
    evidence_text = "\n".join(
        f"[{item.evidence_id}] {render_untrusted_text(item.text, source_id=item.evidence_id)}"
        for item in evidence
    ) or "none"
    social_text = "\n".join(f"{edge.edge_id}: trust={edge.trust}" for edge in relationships) or "none"
    tool_ids = entitlement.tool_ids if entitlement else ()
    patch_text = "; ".join(patch.allowed_context_notes) if patch.status == "ACTIVE" else "NO_PATCH"
    sections = (
        _context_section(
            step=step, section_type="TRIGGER", priority=100, mandatory=True,
            text=trigger_text, tokenizer=tokenizer,
            references=(stimulus.stimulus_id,) if stimulus else (),
        ),
        _context_section(
            step=step, section_type="PERSON_IDENTITY", priority=90, mandatory=True,
            text=(f"person_id={person.person_id}; role={person.role}; "
                  f"objective={person.objective}; attention={person.current_attention}"),
            tokenizer=tokenizer,
        ),
        _context_section(
            step=step, section_type="PRIOR_BELIEFS", priority=80, mandatory=True,
            text=belief_text, tokenizer=tokenizer,
            items=tuple(item.proposition_id for item in beliefs),
        ),
        _context_section(
            step=step, section_type="RETRIEVED_EVIDENCE", priority=70, mandatory=False,
            text=evidence_text, tokenizer=tokenizer,
            items=tuple(item.evidence_id for item in evidence),
            references=tuple(ref for item in evidence for ref in item.evidence_refs),
        ),
        _context_section(
            step=step, section_type="SOCIAL_CONTEXT", priority=50, mandatory=False,
            text=social_text, tokenizer=tokenizer,
            items=tuple(edge.edge_id for edge in relationships),
        ),
        _context_section(
            step=step, section_type="TOOL_ENTITLEMENTS", priority=40, mandatory=True,
            text=", ".join(tool_ids) or "none", tokenizer=tokenizer, items=tool_ids,
        ),
        _context_section(
            step=step, section_type="ACTIVE_POLICY_PATCH", priority=30, mandatory=False,
            text=patch_text, tokenizer=tokenizer,
            items=(patch.patch_id,) if patch.patch_id else (),
        ),
    )
    return tuple(sorted(sections, key=lambda section: -section.priority))


def _build_person_context(
    *,
    schedule: CognitiveSchedule,
    step: ScheduleStep,
    person: PersonState,
    stimulus: Stimulus | None,
    beliefs: tuple[Belief, ...],
    evidence: tuple[RetrievedEvidence, ...],
    relationships: tuple[SocialEdge, ...],
    entitlement: Entitlement | None,
    patch: RetroPatch,
    tokenizer: TokenizerPort,
) -> PersonContext:
    sections = _build_context_sections(
        step=step, person=person, stimulus=stimulus, beliefs=beliefs,
        evidence=evidence, relationships=relationships, entitlement=entitlement,
        patch=patch, tokenizer=tokenizer,
    )
    retrieval_lineage = tuple(item.lineage_ids[0] for item in evidence if item.lineage_ids)
    lineage = tuple(dict.fromkeys(step.source_lineage_ids + retrieval_lineage))
    context = PersonContext(
        context_id=stable_id("context", schedule.run_id, schedule.cycle_id, step.schedule_step_id),
        schedule_step_id=step.schedule_step_id,
        person_id=step.person_id,
        trigger_type=step.trigger_type,
        activation_id=step.activation_id,
        stimulus_id=step.stimulus_id,
        as_of=schedule.as_of,
        sections=sections,
        entitled_tool_ids=entitlement.tool_ids if entitlement else (),
        source_lineage_ids=lineage,
        content_hash="0" * 64,
    )
    return context.model_copy(
        update={
            "content_hash": sha256_value(
                context.model_dump(mode="json", exclude={"content_hash"})
            )
        }
    )


def assemble_context(
    schedule: CognitiveSchedule,
    stimuli: StimulusPanel,
    activations: ActivationPanel,
    states: PersonStatePanel,
    beliefs: BeliefPanel,
    retrieved: RetrievalBundle,
    social: SocialGraph,
    entitlements: EntitlementPanel,
    patch: RetroPatch,
    tokenizer: TokenizerPort,
) -> ContextBundle:
    """Assemble typed context through selection, section building and validation stages."""

    state_by_person = {record.person_id: record for record in states.records}
    stimulus_by_id = {record.stimulus_id: record for record in stimuli.records}
    activation_by_id = {record.activation_id: record for record in activations.records}
    entitlement_by_person = {record.person_id: record for record in entitlements.records}
    contexts: list[PersonContext] = []

    for step in schedule.records:
        person = state_by_person.get(step.person_id)
        if person is None:
            raise S20LineageError(f"schedule references missing person {step.person_id}")
        if step.activation_id and step.activation_id not in activation_by_id:
            raise S20LineageError(f"schedule references missing activation {step.activation_id}")
        stimulus = stimulus_by_id.get(step.stimulus_id) if step.stimulus_id else None
        relationships = tuple(
            edge for edge in social.records
            if step.person_id in (edge.source_person_id, edge.target_person_id)
            and edge.available_at <= schedule.as_of
        )
        prior_beliefs = tuple(
            belief for belief in beliefs.records
            if belief.person_id == step.person_id and belief.available_at <= schedule.as_of
        )
        person_evidence = tuple(
            record for record in retrieved.records if record.person_id == step.person_id
        )
        contexts.append(
            _build_person_context(
                schedule=schedule, step=step, person=person, stimulus=stimulus,
                beliefs=prior_beliefs, evidence=person_evidence, relationships=relationships,
                entitlement=entitlement_by_person.get(step.person_id),
                patch=patch, tokenizer=tokenizer,
            )
        )

    return ContextBundle(
        schema_version="person_context_bundle.v1",
        run_id=schedule.run_id,
        cycle_id=schedule.cycle_id,
        records=tuple(contexts),
        content_hash=sha256_value([item.model_dump(mode="json") for item in contexts]),
        status=Status.READY if contexts else Status.READY_EMPTY,
    )


def _trim_context_sections(context: PersonContext, config: BudgetConfig, budget: int):
    sections = list(context.sections)
    removed_sections: list[str] = []
    removed_items: list[str] = []
    reasons: dict[str, str] = {}
    for section_type in config.removable_section_order:
        if sum(s.estimated_tokens for s in sections) <= budget:
            break
        candidates = [s for s in sections if s.section_type == section_type and not s.mandatory]
        for section in candidates:
            sections.remove(section)
            removed_sections.append(section.section_id)
            removed_items.extend(section.item_ids)
            reasons[section.section_id] = f"removed_by_budget_priority:{section_type}"
            if sum(s.estimated_tokens for s in sections) <= budget:
                break
    return sections, removed_sections, removed_items, reasons


def _validated_context_record(
    context: PersonContext,
    config: BudgetConfig,
    cutoff: CutoffReport,
    tokenizer: TokenizerPort,
    effective_budget: int,
) -> tuple[ValidatedContext, str | None]:
    original_tokens = sum(s.estimated_tokens for s in context.sections)
    sections, removed_sections, removed_items, reasons = _trim_context_sections(context, config, effective_budget)
    final_tokens = sum(s.estimated_tokens for s in sections)
    if final_tokens > effective_budget:
        raise S20BudgetError(f"mandatory context exceeds budget for {context.context_id}")
    evidence_count = sum(
        1 for section in sections
        if section.section_type == "RETRIEVED_EVIDENCE" and section.text != "none"
    )
    evidence_status = "PASS" if evidence_count >= config.minimum_evidence_items else "DEGRADED_INSUFFICIENT_EVIDENCE"
    updated = context.model_copy(update={
        "sections": tuple(sections),
        "content_hash": sha256_value([section.model_dump(mode="json") for section in sections]),
    })
    report = BudgetReport(
        context_id=context.context_id, model_id=cutoff.model_id, tokenizer_ref=tokenizer.ref,
        original_tokens=original_tokens, effective_budget=effective_budget, final_tokens=final_tokens,
        removed_section_ids=tuple(removed_sections), removed_item_ids=tuple(removed_items),
        removed_section_reasons=reasons, minimum_evidence_status=evidence_status, cutoff_risk=cutoff.risk,
    )
    warning = f"{context.context_id}:{evidence_status}" if evidence_status != "PASS" else None
    return ValidatedContext(context=updated, budget_report=report), warning


def validate_budget(
    bundle: ContextBundle,
    config: BudgetConfig,
    cutoff: CutoffReport,
    tokenizer: TokenizerPort,
) -> ValidatedContextBundle:
    """Apply model-aware budgets and report every removed section."""
    if cutoff.risk == CutoffRisk.BLOCK:
        raise S20BudgetError("model cutoff risk blocks context")
    effective_budget = min(
        config.max_input_tokens,
        cutoff.model_context_window - config.reserved_output_tokens - config.safety_margin_tokens,
    )
    if effective_budget <= 0:
        raise S20BudgetError("non-positive effective budget")
    validated: list[ValidatedContext] = []
    warnings: list[str] = []
    for context in bundle.records:
        item, warning = _validated_context_record(context, config, cutoff, tokenizer, effective_budget)
        validated.append(item)
        if warning:
            warnings.append(warning)
    status = Status.DEGRADED if warnings else Status.READY if validated else Status.READY_EMPTY
    return ValidatedContextBundle(
        schema_version="validated_person_context_bundle.v1", run_id=bundle.run_id,
        cycle_id=bundle.cycle_id, records=tuple(validated),
        content_hash=sha256_value([r.model_dump(mode="json") for r in validated]),
        status=status, warnings=tuple(warnings),
    )
