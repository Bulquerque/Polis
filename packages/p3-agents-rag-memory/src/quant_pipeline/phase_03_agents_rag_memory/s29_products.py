from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
from math import fsum
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .s29_models import (
    AgentDisagreementPanel,
    AgentDisagreementRecord,
    AgentReadingPanel,
    BeliefDistributionPanel,
    BeliefDistributionRecord,
    BeliefUpdateRecord,
    ClaimRecord,
    DisagreementSemanticsConfig,
    EvidenceBoundBeliefUpdatePanel,
    EvidenceKind,
    EvidenceReference,
    EvidenceTagPanel,
    EvidenceTagRecord,
    ExecutionContext,
    GraphEvidenceMap,
    QualityStatus,
    RagIndexArtifact,
    RagIndexEntry,
    RetrievalEvidenceMap,
    SocietyStateRecord,
    ValidatedSocietyStatePanel,
)


class S29Error(ValueError):
    """Base error for deterministic S29 contract and semantic failures."""


class S29ContractError(S29Error):
    """Raised when an input or output violates a declared contract."""


class S29TemporalError(S29ContractError):
    """Raised when point-in-time integrity is violated."""


class S29LineageError(S29ContractError):
    """Raised when a claim or evidence chain cannot be resolved exactly."""


FORBIDDEN_FIELDS = frozenset(
    {
        "target",
        "future_return",
        "label",
        "prediction",
        "candidate_id",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "realized_pnl",
        "buy_sell_signal",
        "signal_direction",
    }
)

ModelT = TypeVar("ModelT", bound=BaseModel)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="json"))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _stable_hash(value: Any) -> str:
    blob = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _scan_forbidden(value: Any, path: str = "root") -> None:
    if isinstance(value, BaseModel):
        _scan_forbidden(value.model_dump(mode="python"), path)
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_str = str(key)
            if key_str in FORBIDDEN_FIELDS:
                raise S29ContractError(f"forbidden field detected at {path}.{key_str}")
            _scan_forbidden(child, f"{path}.{key_str}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]")


def _parse(model: type[ModelT], value: Any, name: str) -> ModelT:
    try:
        if isinstance(value, BaseModel):
            return model.model_validate(value, strict=True)
        blob = json.dumps(
            _canonical_value(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return model.model_validate_json(blob, strict=True)
    except (ValidationError, TypeError, ValueError) as exc:
        raise S29ContractError(f"{name} failed strict validation: {exc}") from exc


def _validate_context_alignment(context: ExecutionContext, artifacts: Sequence[BaseModel]) -> None:
    for artifact in artifacts:
        payload = artifact.model_dump(mode="python")
        for field in ("run_id", "cycle_id", "as_of_time", "pipeline_version"):
            expected = getattr(context, field)
            actual = payload.get(field)
            if actual != expected:
                raise S29ContractError(
                    f"artifact {payload.get('artifact_id', '<unknown>')} has {field}={actual!r}; "
                    f"expected {expected!r}"
                )


def _unique_index(records: Sequence[ModelT], key_fn, name: str) -> dict[Any, ModelT]:  # type: ignore[no-untyped-def]
    result: dict[Any, ModelT] = {}
    for record in records:
        key = key_fn(record)
        if key in result:
            raise S29ContractError(f"duplicate {name} key: {key!r}")
        result[key] = record
    return result


def _quality_rollup(statuses: Sequence[QualityStatus]) -> QualityStatus:
    if any(status == QualityStatus.BLOCKED for status in statuses):
        return QualityStatus.BLOCKED
    if any(status == QualityStatus.DEGRADED for status in statuses):
        return QualityStatus.DEGRADED
    return QualityStatus.PASS


def _round(value: float, precision: int) -> float:
    rounded = round(value, precision)
    if rounded < 0.0 and abs(rounded) < 10 ** (-precision):
        return 0.0
    return min(1.0, max(0.0, rounded))


def _lineage_id(prefix: str, payload: Any) -> str:
    return f"lineage-{prefix}-{_stable_hash(payload)[:20]}"


def _artifact_id(prefix: str, payload: Any) -> str:
    return f"{prefix}-{_stable_hash(payload)[:20]}"


def _module_result(
    *,
    module_id: str,
    module_name: str,
    output_name: str,
    output: BaseModel,
    started_at: float,
) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "phase_03_agents_rag_memory",
        "subphase": "P3.S29",
        "implementation_status": "IMPLEMENTED_QUALIFIED_INTERNAL",
        "outputs": {output_name: output.model_dump(mode="json")},
        "observability": {
            "events": ["module_started", "input_contract_validated", "module_succeeded"],
            "duration_ms": round((perf_counter() - started_at) * 1000.0, 3),
            "output_record_count": len(getattr(output, "records", ())),
            "warning_count": sum(
                1
                for record in getattr(output, "records", ())
                if getattr(record, "quality_status", QualityStatus.PASS) != QualityStatus.PASS
            ),
            "error_count": 0,
        },
    }



def _parse_disagreement_inputs(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
) -> tuple[ExecutionContext, BeliefDistributionPanel, ValidatedSocietyStatePanel, DisagreementSemanticsConfig]:
    required = {
        "belief_distribution_panel",
        "validated_society_state_panel",
        "aggregation_semantics_config",
    }
    missing = sorted(required.difference(inputs))
    if missing:
        raise S29ContractError(f"P3.S29.M01 missing required inputs: {missing}")
    context = _parse(ExecutionContext, context_value, "execution_context")
    belief_panel = _parse(BeliefDistributionPanel, inputs["belief_distribution_panel"], "belief_distribution_panel")
    society_panel = _parse(ValidatedSocietyStatePanel, inputs["validated_society_state_panel"], "validated_society_state_panel")
    semantics = _parse(DisagreementSemanticsConfig, inputs["aggregation_semantics_config"], "aggregation_semantics_config")
    _validate_context_alignment(context, (belief_panel, society_panel))
    return context, belief_panel, society_panel, semantics


def _aligned_disagreement_indexes(
    belief_panel: BeliefDistributionPanel,
    society_panel: ValidatedSocietyStatePanel,
) -> tuple[dict[Any, BeliefDistributionRecord], dict[Any, SocietyStateRecord]]:
    belief_by_key = _unique_index(belief_panel.records, lambda item: item.grain_key, "belief distribution")
    society_by_key = _unique_index(society_panel.records, lambda item: item.grain_key, "society state")
    if set(belief_by_key) != set(society_by_key):
        missing_society = sorted(str(key) for key in set(belief_by_key) - set(society_by_key))
        missing_belief = sorted(str(key) for key in set(society_by_key) - set(belief_by_key))
        raise S29ContractError(
            "grain mismatch between belief_distribution_panel and validated_society_state_panel; "
            f"missing_society={missing_society}, missing_belief={missing_belief}"
        )
    return belief_by_key, society_by_key


def _disagreement_quality(
    belief: BeliefDistributionRecord,
    society: SocietyStateRecord,
    semantics: DisagreementSemanticsConfig,
) -> tuple[QualityStatus, list[str], float, float]:
    reasons = list(society.quality_reasons)
    status = society.quality_status
    coverage = min(belief.coverage_ratio, society.coverage_ratio)
    quality = min(belief.source_quality_score, society.source_quality_score)
    if belief.effective_sample_size < semantics.min_effective_sample_size:
        status = QualityStatus.BLOCKED
        reasons.append("EFFECTIVE_SAMPLE_SIZE_BELOW_MINIMUM")
    if coverage < semantics.min_coverage_ratio:
        status = QualityStatus.BLOCKED
        reasons.append("COVERAGE_BELOW_MINIMUM")
    if society.quality_status in semantics.blocked_quality_statuses:
        status = QualityStatus.BLOCKED
        reasons.append("UPSTREAM_QUALITY_BLOCKED")
    if quality < semantics.min_source_quality_score and status != QualityStatus.BLOCKED:
        status = QualityStatus.DEGRADED
        reasons.append("SOURCE_QUALITY_BELOW_PREFERRED_MINIMUM")
    return status, reasons, coverage, quality


def _disagreement_record(
    *,
    context: ExecutionContext,
    belief: BeliefDistributionRecord,
    society: SocietyStateRecord,
    semantics: DisagreementSemanticsConfig,
) -> AgentDisagreementRecord:
    if belief.as_of_time > context.as_of_time or society.as_of_time > context.as_of_time:
        raise S29TemporalError(f"input as_of_time exceeds execution as_of_time at grain {belief.grain_key!r}")
    variance = min(1.0, belief.belief_variance / semantics.variance_cap)
    components = {
        "direction": belief.normalized_entropy,
        "variance": variance,
        "polarization": belief.polarization,
        "confidence": society.confidence_dispersion,
        "evidence": society.evidence_diversity,
    }
    status, reasons, coverage, quality = _disagreement_quality(belief, society, semantics)
    disagreement = None
    agreement = None
    if status != QualityStatus.BLOCKED:
        weights = semantics.weights
        disagreement = _round(fsum((
            weights.direction_entropy * components["direction"],
            weights.belief_variance * components["variance"],
            weights.polarization * components["polarization"],
            weights.confidence_dispersion * components["confidence"],
            weights.evidence_diversity * components["evidence"],
        )), semantics.output_precision)
        agreement = _round(1.0 - disagreement, semantics.output_precision)
    unique_reasons = tuple(sorted(set(reasons)))
    payload = {
        "grain": belief.grain_key,
        "components": components,
        "formula_id": semantics.formula_id,
        "formula_version": semantics.formula_version,
        "quality_status": status,
        "quality_reasons": unique_reasons,
        "input_lineage": sorted((belief.lineage_id, society.lineage_id)),
    }
    return AgentDisagreementRecord(
        date=context.as_of_time.date(), as_of_date=context.as_of_time.date(), available_at=context.created_at,
        underlying=belief.underlying_id, proposition_id=belief.proposition_id, horizon=belief.horizon,
        disagreement_score=disagreement, agent_agreement_score=agreement,
        direction_disagreement_score=_round(belief.normalized_entropy, semantics.output_precision),
        confidence_disagreement_score=_round(society.confidence_dispersion, semantics.output_precision),
        evidence_disagreement_score=_round(society.evidence_diversity, semantics.output_precision),
        polarization_score=_round(belief.polarization, semantics.output_precision),
        belief_variance_score=_round(variance, semantics.output_precision),
        effective_sample_size=belief.effective_sample_size, population_size=belief.population_size,
        coverage_ratio=coverage, source_quality_score=quality,
        formula_id=semantics.formula_id, formula_version=semantics.formula_version,
        quality_status=status, quality_reasons=unique_reasons,
        lineage_id=_lineage_id("agent-disagreement-record", payload),
    )


def build_agent_disagreement_panel(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic legacy-compatible disagreement product."""
    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    context, belief_panel, society_panel, semantics = _parse_disagreement_inputs(inputs, context_value)
    belief_by_key, society_by_key = _aligned_disagreement_indexes(belief_panel, society_panel)
    keys = sorted(belief_by_key, key=lambda item: tuple(str(part) for part in item))
    records = tuple(
        _disagreement_record(
            context=context,
            belief=belief_by_key[key],
            society=society_by_key[key],
            semantics=semantics,
        )
        for key in keys
    )
    artifact_payload = [record.model_dump(mode="json") for record in records]
    output = AgentDisagreementPanel(
        artifact_id=_artifact_id("agent-disagreement-panel", artifact_payload),
        created_at=context.created_at,
        lineage_id=_lineage_id("agent-disagreement-panel", {
            "belief_panel": belief_panel.lineage_id,
            "society_panel": society_panel.lineage_id,
            "formula": (semantics.formula_id, semantics.formula_version),
            "records": artifact_payload,
        }),
        pipeline_version=context.pipeline_version,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        schema_id="p3.s29.agent_disagreement_panel.semantic",
        schema_version="1.0.0",
        quality_status=_quality_rollup([record.quality_status for record in records]),
        quality_reasons=tuple(sorted({reason for record in records for reason in record.quality_reasons})),
        records=records,
    )
    _scan_forbidden(output)
    return _module_result(
        module_id="P3.S29.M01",
        module_name="agent_disagreement_panel_builder",
        output_name="agent_disagreement_panel",
        output=output,
        started_at=started_at,
    )

def _evidence_index(
    retrieval: RetrievalEvidenceMap,
    graph: GraphEvidenceMap,
) -> dict[str, EvidenceReference]:
    result: dict[str, EvidenceReference] = {}
    for source_name, records in (
        ("retrieval_evidence_map", retrieval.records),
        ("graph_evidence_map", graph.records),
    ):
        for record in records:
            if record.evidence_id in result:
                raise S29LineageError(
                    f"evidence_id {record.evidence_id!r} appears in multiple evidence maps"
                )
            result[record.evidence_id] = record
    return result


def _parse_evidence_claim_inputs(
    inputs: Mapping[str, Any], context_value: Mapping[str, Any]
) -> tuple[
    ExecutionContext, EvidenceBoundBeliefUpdatePanel, RetrievalEvidenceMap,
    GraphEvidenceMap, RagIndexArtifact, AgentReadingPanel
]:
    required = {
        "evidence_bound_belief_update_panel", "retrieval_evidence_map", "graph_evidence_map",
        "rag_index_artifact", "agent_reading_panel",
    }
    missing = sorted(required.difference(inputs))
    if missing:
        raise S29ContractError(f"P3.S29.M02 missing required inputs: {missing}")
    context = _parse(ExecutionContext, context_value, "execution_context")
    artifacts = (
        _parse(EvidenceBoundBeliefUpdatePanel, inputs["evidence_bound_belief_update_panel"], "evidence_bound_belief_update_panel"),
        _parse(RetrievalEvidenceMap, inputs["retrieval_evidence_map"], "retrieval_evidence_map"),
        _parse(GraphEvidenceMap, inputs["graph_evidence_map"], "graph_evidence_map"),
        _parse(RagIndexArtifact, inputs["rag_index_artifact"], "rag_index_artifact"),
        _parse(AgentReadingPanel, inputs["agent_reading_panel"], "agent_reading_panel"),
    )
    _validate_context_alignment(context, artifacts)
    return (context, *artifacts)


def _claims_grouped_by_belief(
    readings: AgentReadingPanel, belief_by_id: Mapping[str, BeliefUpdateRecord]
) -> dict[str, list[ClaimRecord]]:
    claim_by_id = _unique_index(readings.records, lambda item: item.claim_id, "claim")
    grouped: dict[str, list[ClaimRecord]] = {}
    for claim in claim_by_id.values():
        grouped.setdefault(claim.belief_update_id, []).append(claim)
    if orphan_claims := sorted(set(grouped) - set(belief_by_id)):
        raise S29LineageError(f"orphan claims reference unknown belief updates: {orphan_claims}")
    return grouped


def _validate_claim_matches_belief(
    claim: ClaimRecord, belief: BeliefUpdateRecord, context: ExecutionContext
) -> None:
    fields = ("person_id", "run_id", "cycle_id", "underlying_id", "proposition_id", "horizon")
    if any(getattr(claim, field) != getattr(belief, field) for field in fields):
        raise S29LineageError(
            f"claim {claim.claim_id!r} does not match belief update {belief.belief_update_id!r} grain"
        )
    if claim.created_at > context.as_of_time:
        raise S29TemporalError(f"claim {claim.claim_id!r} is future-dated")


def _validate_rag_reference(
    evidence: EvidenceReference, rag_by_chunk: Mapping[str, RagIndexEntry], context: ExecutionContext
) -> None:
    if evidence.evidence_kind != EvidenceKind.RAG_CHUNK:
        return
    chunk = rag_by_chunk.get(evidence.chunk_id)
    if chunk is None:
        raise S29LineageError(
            f"RAG evidence {evidence.evidence_id!r} references missing chunk {evidence.chunk_id!r}"
        )
    if (chunk.document_id, chunk.source_id, chunk.content_hash) != (
        evidence.document_id, evidence.source_id, evidence.content_hash
    ):
        raise S29LineageError(
            f"RAG evidence {evidence.evidence_id!r} does not match the canonical index entry"
        )
    if chunk.available_at > context.as_of_time:
        raise S29TemporalError(f"RAG chunk {chunk.chunk_id!r} became available after as_of_time")


def _evidence_record(
    *, context: ExecutionContext, belief: BeliefUpdateRecord, claim: ClaimRecord,
    evidence: EvidenceReference
) -> EvidenceTagRecord:
    quality_status = QualityStatus.PASS if evidence.source_quality_score >= 0.5 else QualityStatus.DEGRADED
    quality_reasons = () if quality_status == QualityStatus.PASS else ("LOW_SOURCE_QUALITY",)
    lineage_payload = {
        "belief_update": belief.belief_update_id, "claim": claim.claim_id,
        "evidence": evidence.evidence_id, "relation": claim.relation,
        "claim_lineage": claim.lineage_id, "belief_lineage": belief.lineage_id,
        "evidence_lineage": evidence.lineage_id,
    }
    return EvidenceTagRecord(
        date=context.as_of_time.date(), as_of_date=context.as_of_time.date(),
        available_at=evidence.available_at, underlying=belief.underlying_id,
        proposition_id=belief.proposition_id, horizon=belief.horizon, person_id=belief.person_id,
        belief_update_id=belief.belief_update_id, claim_id=claim.claim_id,
        evidence_id=evidence.evidence_id, evidence_tag=claim.claim_type,
        evidence_relation=claim.relation, evidence_kind=evidence.evidence_kind,
        source_id=evidence.source_id, document_id=evidence.document_id, chunk_id=evidence.chunk_id,
        graph_path_id=evidence.graph_path_id, content_hash=evidence.content_hash,
        source_quality_score=evidence.source_quality_score, claim_statement_summary=claim.statement_summary,
        quality_status=quality_status, quality_reasons=quality_reasons,
        lineage_id=_lineage_id("evidence-tag-record", lineage_payload),
    )


def _records_for_belief(
    *, belief: BeliefUpdateRecord, claims: Sequence[ClaimRecord],
    evidence_by_id: Mapping[str, EvidenceReference], rag_by_chunk: Mapping[str, RagIndexEntry],
    context: ExecutionContext
) -> list[EvidenceTagRecord]:
    if not claims:
        raise S29LineageError(
            f"belief update {belief.belief_update_id!r} has no structured claim in agent_reading_panel"
        )
    if belief.as_of_time > context.as_of_time:
        raise S29TemporalError(f"belief update {belief.belief_update_id!r} is future-dated")
    referenced: set[str] = set()
    records: list[EvidenceTagRecord] = []
    for claim in sorted(claims, key=lambda item: item.claim_id):
        _validate_claim_matches_belief(claim, belief, context)
        for evidence_id in sorted(claim.evidence_refs):
            referenced.add(evidence_id)
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                raise S29LineageError(
                    f"claim {claim.claim_id!r} references missing evidence {evidence_id!r}"
                )
            if evidence.available_at > context.as_of_time:
                raise S29TemporalError(
                    f"evidence {evidence_id!r} became available after as_of_time"
                )
            _validate_rag_reference(evidence, rag_by_chunk, context)
            records.append(_evidence_record(context=context, belief=belief, claim=claim, evidence=evidence))
    declared = set(belief.all_evidence_refs)
    if referenced != declared:
        raise S29LineageError(
            f"belief update {belief.belief_update_id!r} evidence binding mismatch; "
            f"missing_from_claims={sorted(declared - referenced)}, "
            f"undeclared_in_belief={sorted(referenced - declared)}"
        )
    return records


def _build_evidence_tag_panel(
    *, context: ExecutionContext, belief_panel: EvidenceBoundBeliefUpdatePanel,
    retrieval: RetrievalEvidenceMap, graph: GraphEvidenceMap, rag: RagIndexArtifact,
    readings: AgentReadingPanel, records: list[EvidenceTagRecord]
) -> EvidenceTagPanel:
    records.sort(key=lambda item: (
        item.underlying, item.proposition_id, item.horizon, item.person_id,
        item.belief_update_id, item.claim_id, item.evidence_id,
    ))
    status = _quality_rollup([record.quality_status for record in records])
    reasons = tuple(sorted({reason for record in records for reason in record.quality_reasons}))
    payload = [record.model_dump(mode="json") for record in records]
    return EvidenceTagPanel(
        artifact_id=_artifact_id("evidence-tag-panel", payload), created_at=context.created_at,
        lineage_id=_lineage_id("evidence-tag-panel", {
            "belief_panel": belief_panel.lineage_id, "retrieval_map": retrieval.lineage_id,
            "graph_map": graph.lineage_id, "rag_index": rag.lineage_id,
            "readings": readings.lineage_id, "records": payload,
        }),
        pipeline_version=context.pipeline_version, run_id=context.run_id, cycle_id=context.cycle_id,
        as_of_time=context.as_of_time, schema_id="p3.s29.evidence_tag_panel.semantic",
        schema_version="1.0.0", quality_status=status, quality_reasons=reasons, records=tuple(records),
    )


def extract_evidence_claims(
    inputs: Mapping[str, Any], context_value: Mapping[str, Any]
) -> dict[str, Any]:
    """Project the claim-to-evidence chain without semantic invention."""
    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    context, belief_panel, retrieval, graph, rag, readings = _parse_evidence_claim_inputs(
        inputs, context_value
    )
    belief_by_id = _unique_index(
        belief_panel.records, lambda item: item.belief_update_id, "belief update"
    )
    claims_by_update = _claims_grouped_by_belief(readings, belief_by_id)
    evidence_by_id = _evidence_index(retrieval, graph)
    rag_by_chunk = _unique_index(rag.records, lambda item: item.chunk_id, "RAG chunk")
    records = [
        record
        for belief_id in sorted(belief_by_id)
        for record in _records_for_belief(
            belief=belief_by_id[belief_id], claims=claims_by_update.get(belief_id, []),
            evidence_by_id=evidence_by_id, rag_by_chunk=rag_by_chunk, context=context,
        )
    ]
    output = _build_evidence_tag_panel(
        context=context, belief_panel=belief_panel, retrieval=retrieval, graph=graph,
        rag=rag, readings=readings, records=records,
    )
    _scan_forbidden(output)
    return _module_result(
        module_id="P3.S29.M02", module_name="evidence_claim_extractor",
        output_name="evidence_tag_panel", output=output, started_at=started_at,
    )

