"""Learning handoff validation and candidate reconciliation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypeVar

from pydantic import BaseModel, ValidationError

from ..artifacts import validate_artifact_integrity
from ..boundary.base import ArtifactEnvelope, HandoffManifestRecord
from ..boundary.inputs import (
    ComparisonGroupRecord,
    ConfidenceRecord,
    HybridScoreRecord,
    PreFinalBlockedRecord,
    StrategyReferenceRecord,
)
from ..domain.models import Candidate
from ..errors import ContractViolation, ErrorContext, IntegrityViolation, TemporalViolation

T = TypeVar("T", bound=BaseModel)
REQUIRED_ARTIFACTS = (
    "hybrid_candidate_score_panel",
    "candidate_score_confidence_panel",
    "score_decomposition_panel",
    "comparison_group_panel",
    "validated_strategy_candidate_reference_panel",
    "pre_final_blocked_candidate_panel",
)


@dataclass(frozen=True, slots=True)
class LearningBundle:
    manifest: ArtifactEnvelope
    artifacts: Mapping[str, ArtifactEnvelope]
    candidates: tuple[Candidate, ...]
    preblocks: Mapping[str, PreFinalBlockedRecord]


@dataclass(frozen=True, slots=True)
class CandidateMaps:
    scores: Mapping[str, HybridScoreRecord]
    confidences: Mapping[str, ConfidenceRecord]
    groups: Mapping[str, ComparisonGroupRecord]
    references: Mapping[str, StrategyReferenceRecord]
    preblocks: Mapping[str, PreFinalBlockedRecord]


def _parse_artifact(raw: object, name: str, module_id: str) -> ArtifactEnvelope:
    try:
        envelope = ArtifactEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise ContractViolation("P7_ARTIFACT_SCHEMA_INVALID", f"invalid {name}: {exc}", ErrorContext(module_id)) from exc
    if envelope.artifact_name != name:
        context = ErrorContext(module_id, (envelope.artifact_id,))
        raise ContractViolation("P7_ARTIFACT_NAME_MISMATCH", f"expected {name}", context)
    validate_artifact_integrity(envelope, module_id)
    return envelope


def _parse_records(envelope: ArtifactEnvelope, model: type[T], module_id: str) -> tuple[T, ...]:
    parsed: list[T] = []
    for index, record in enumerate(envelope.records):
        try:
            parsed.append(model.model_validate(record))
        except ValidationError as exc:
            message = f"invalid record {index} in {envelope.artifact_name}: {exc}"
            raise ContractViolation(
                "P7_RECORD_SCHEMA_INVALID",
                message,
                ErrorContext(module_id, (envelope.artifact_id,)),
            ) from exc
    return tuple(parsed)


def _index_unique(records: tuple[T, ...], module_id: str) -> dict[str, T]:
    indexed: dict[str, T] = {}
    for record in records:
        candidate_id = str(getattr(record, "candidate_id"))
        if candidate_id in indexed:
            context = ErrorContext(module_id, candidate_ids=(candidate_id,))
            raise IntegrityViolation("P7_DUPLICATE_CANDIDATE_ID", candidate_id, context)
        indexed[candidate_id] = record
    return indexed


def _scan_forbidden(value: object, forbidden: frozenset[str], path: str = "$") -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key) in forbidden:
                found.append(child)
            found.extend(_scan_forbidden(item, forbidden, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_scan_forbidden(item, forbidden, f"{path}[{index}]"))
    return tuple(found)


def _load_manifest(inputs: Mapping[str, object], module_id: str) -> tuple[ArtifactEnvelope, HandoffManifestRecord]:
    name = "hybrid_scoring_handoff_manifest"
    if name not in inputs:
        raise ContractViolation("P7_HANDOFF_MANIFEST_MISSING", "learning manifest missing", ErrorContext(module_id))
    manifest = _parse_artifact(inputs[name], name, module_id)
    records = _parse_records(manifest, HandoffManifestRecord, module_id)
    if len(records) != 1:
        raise ContractViolation("P7_HANDOFF_MANIFEST_CARDINALITY", "manifest must have one record", ErrorContext(module_id))
    return manifest, records[0]


def _load_referenced_artifacts(
    inputs: Mapping[str, object],
    module_id: str,
    manifest: ArtifactEnvelope,
    record: HandoffManifestRecord,
) -> dict[str, ArtifactEnvelope]:
    refs = {ref.artifact_name: ref for ref in record.artifact_references}
    if set(REQUIRED_ARTIFACTS) - set(refs):
        raise ContractViolation("P7_HANDOFF_REFERENCE_MISSING", "manifest misses required artifact", ErrorContext(module_id))
    artifacts: dict[str, ArtifactEnvelope] = {}
    for name in REQUIRED_ARTIFACTS:
        if name not in inputs:
            raise ContractViolation("P7_INPUT_ARTIFACT_MISSING", name, ErrorContext(module_id))
        envelope = _parse_artifact(inputs[name], name, module_id)
        expected = refs[name]
        actual = (envelope.artifact_id, envelope.content_sha256, envelope.schema_version, envelope.record_count)
        reference = (expected.artifact_id, expected.content_sha256, expected.schema_version, expected.record_count)
        if actual != reference:
            context = ErrorContext(module_id, (envelope.artifact_id,))
            raise IntegrityViolation("P7_HANDOFF_REFERENCE_MISMATCH", name, context)
        if envelope.cycle_id != manifest.cycle_id or envelope.decision_time != manifest.decision_time:
            context = ErrorContext(module_id, (envelope.artifact_id,))
            raise TemporalViolation("P7_HANDOFF_CLOCK_MISMATCH", name, context)
        artifacts[name] = envelope
    return artifacts


def _parse_candidate_maps(artifacts: Mapping[str, ArtifactEnvelope], module_id: str) -> CandidateMaps:
    scores = _index_unique(_parse_records(artifacts["hybrid_candidate_score_panel"], HybridScoreRecord, module_id), module_id)
    confidences = _index_unique(
        _parse_records(artifacts["candidate_score_confidence_panel"], ConfidenceRecord, module_id), module_id
    )
    groups = _index_unique(_parse_records(artifacts["comparison_group_panel"], ComparisonGroupRecord, module_id), module_id)
    references = _index_unique(
        _parse_records(artifacts["validated_strategy_candidate_reference_panel"], StrategyReferenceRecord, module_id),
        module_id,
    )
    preblocks = _index_unique(
        _parse_records(artifacts["pre_final_blocked_candidate_panel"], PreFinalBlockedRecord, module_id), module_id
    )
    return CandidateMaps(scores, confidences, groups, references, preblocks)


def _validate_candidate_maps(maps: CandidateMaps, expected_count: int, module_id: str) -> None:
    candidate_sets = [set(maps.scores), set(maps.confidences), set(maps.groups), set(maps.references)]
    if any(candidate_set != candidate_sets[0] for candidate_set in candidate_sets[1:]):
        raise IntegrityViolation("P7_CANDIDATE_RECONCILIATION_FAILED", "candidate sets differ", ErrorContext(module_id))
    if not set(maps.preblocks).issubset(candidate_sets[0]):
        raise IntegrityViolation("P7_PREBLOCK_UNKNOWN_CANDIDATE", "preblock references unknown candidate", ErrorContext(module_id))
    if expected_count != len(maps.scores):
        message = f"manifest={expected_count} actual={len(maps.scores)}"
        raise IntegrityViolation("P7_MANIFEST_CANDIDATE_COUNT_MISMATCH", message, ErrorContext(module_id))


def _build_candidate(candidate_id: str, maps: CandidateMaps, module_id: str) -> Candidate:
    score = maps.scores[candidate_id]
    confidence = maps.confidences[candidate_id]
    group = maps.groups[candidate_id]
    reference = maps.references[candidate_id]
    context = ErrorContext(module_id, candidate_ids=(candidate_id,))
    if len({score.cycle_id, confidence.cycle_id, group.cycle_id, reference.cycle_id}) != 1:
        raise TemporalViolation("P7_RECORD_CYCLE_MISMATCH", candidate_id, context)
    if len({score.decision_time, confidence.decision_time, group.decision_time, reference.decision_time}) != 1:
        raise TemporalViolation("P7_RECORD_DECISION_TIME_MISMATCH", candidate_id, context)
    if group.comparison_group_id != score.comparison_group_id or reference.comparison_group_id != score.comparison_group_id:
        raise IntegrityViolation("P7_COMPARISON_GROUP_MISMATCH", candidate_id, context)
    return Candidate(
        cycle_id=score.cycle_id,
        decision_time=score.decision_time,
        candidate_id=candidate_id,
        comparison_group_id=score.comparison_group_id,
        hybrid_score=score.hybrid_score,
        robust_score=score.robust_score,
        execution_quality=score.execution_quality,
        complexity_score=score.complexity_score,
        score_confidence=confidence.score_confidence,
        interval_lower=confidence.score_interval_lower,
        interval_upper=confidence.score_interval_upper,
        model_disagreement=confidence.model_disagreement,
        calibration_status=confidence.calibration_status,
        calibration_version=confidence.calibration_version,
        ood_severity=confidence.ood_severity,
        model_id=score.model_id,
        model_promotion_status=score.model_promotion_status,
        model_compatibility_status=score.model_compatibility_status,
        score_semantics_version=score.score_semantics_version,
        payoff_shape=reference.payoff_shape,
        scenario_payoff=reference.scenario_payoff,
        greek_vector=reference.greek_vector,
        leg_ids=frozenset(reference.leg_ids),
        origin_template=reference.origin_template,
        expiration_ids=frozenset(reference.expiration_ids),
        defined_risk_status=reference.defined_risk_status,
        execution_context_time=reference.execution_context_time,
        context_available=reference.context_available,
        candidate_identity_hash=reference.candidate_identity_hash,
        strategy_artifact_id=reference.strategy_artifact_id,
        strategy_content_sha256=reference.strategy_content_sha256,
        strategy_schema_version=reference.strategy_schema_version,
        lineage_id=reference.strategy_lineage_id,
        pareto_tier=reference.pareto_tier,
    )


def load_scoring_bundle(
    inputs: Mapping[str, object], module_id: str, forbidden_fields: tuple[str, ...]
) -> LearningBundle:
    manifest, manifest_record = _load_manifest(inputs, module_id)
    artifacts = _load_referenced_artifacts(inputs, module_id, manifest, manifest_record)
    hits = _scan_forbidden(inputs, frozenset(forbidden_fields))
    if hits:
        raise TemporalViolation("P7_FUTURE_FIELD_DETECTED", ", ".join(hits[:5]), ErrorContext(module_id))
    maps = _parse_candidate_maps(artifacts, module_id)
    _validate_candidate_maps(maps, manifest_record.candidate_count, module_id)
    candidates = tuple(_build_candidate(candidate_id, maps, module_id) for candidate_id in sorted(maps.scores))
    return LearningBundle(manifest, artifacts, candidates, maps.preblocks)
