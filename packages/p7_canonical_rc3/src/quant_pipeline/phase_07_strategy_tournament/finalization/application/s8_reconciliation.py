"""Validate and reconcile the frozen S7→S8 content-addressed handoff."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..artifacts import sha256_value
from ..boundary.base import ArtifactEnvelope, HandoffManifestRecord
from ..boundary.inputs import ComparisonGroupRecord, StrategyReferenceRecord
from ..boundary.outputs import (
    AbstainedRecord,
    BlockedRecord,
    DiversityAdjustedScoreRecord,
    DiversityClusterRecord,
    GroupRankabilityRecord,
    RankableRecord,
)
from ..boundary.s8_inputs import ScoreDecompositionRecord
from ..errors import ContractViolation, ErrorContext, IntegrityViolation, TemporalViolation
from .module_io import parse_envelope, parse_records

REQUIRED_ARTIFACTS = (
    "rankable_candidate_panel",
    "abstained_candidate_panel",
    "final_blocked_candidate_panel",
    "rankability_group_report",
    "diversity_adjusted_score_panel",
    "candidate_diversity_cluster_panel",
    "score_decomposition_panel",
    "comparison_group_panel",
    "validated_strategy_candidate_reference_panel",
)


@dataclass(frozen=True, slots=True)
class S8Bundle:
    manifest: ArtifactEnvelope
    manifest_record: HandoffManifestRecord
    artifacts: Mapping[str, ArtifactEnvelope]
    rankable: tuple[RankableRecord, ...]
    abstained: tuple[AbstainedRecord, ...]
    blocked: tuple[BlockedRecord, ...]
    group_reports: tuple[GroupRankabilityRecord, ...]
    adjusted: Mapping[str, DiversityAdjustedScoreRecord]
    clusters: Mapping[str, DiversityClusterRecord]
    groups: Mapping[str, ComparisonGroupRecord]
    strategies: Mapping[str, StrategyReferenceRecord]
    decomposition: Mapping[str, tuple[ScoreDecompositionRecord, ...]]


def _one_manifest(inputs: Mapping[str, object], module_id: str) -> tuple[ArtifactEnvelope, HandoffManifestRecord]:
    envelope = parse_envelope(inputs, "rankability_handoff_manifest", module_id)
    records = parse_records(envelope, HandoffManifestRecord, module_id)
    if len(records) != 1:
        raise ContractViolation("P7_S7_HANDOFF_MANIFEST_CARDINALITY", "expected one manifest record", ErrorContext(module_id))
    record = records[0]
    if record.consumer != "P7.S8" or record.contract_id != "p7_s7_to_s8_rankability_handoff":
        raise ContractViolation("P7_S7_HANDOFF_CONTRACT_INVALID", record.contract_id, ErrorContext(module_id))
    return envelope, record


def _load_artifacts(
    inputs: Mapping[str, object], manifest: ArtifactEnvelope, record: HandoffManifestRecord, module_id: str
) -> dict[str, ArtifactEnvelope]:
    references = {item.artifact_name: item for item in record.artifact_references}
    missing = sorted(set(REQUIRED_ARTIFACTS) - set(references))
    if missing:
        raise ContractViolation("P7_S7_HANDOFF_REFERENCE_MISSING", ",".join(missing), ErrorContext(module_id))
    artifacts: dict[str, ArtifactEnvelope] = {}
    for name in REQUIRED_ARTIFACTS:
        envelope = parse_envelope(inputs, name, module_id)
        ref = references[name]
        observed = (envelope.artifact_id, envelope.content_sha256, envelope.schema_version, envelope.record_count)
        expected = (ref.artifact_id, ref.content_sha256, ref.schema_version, ref.record_count)
        if observed != expected:
            raise IntegrityViolation("P7_S7_HANDOFF_REFERENCE_MISMATCH", name, ErrorContext(module_id, (envelope.artifact_id,)))
        if envelope.cycle_id != manifest.cycle_id or envelope.decision_time != manifest.decision_time:
            raise TemporalViolation("P7_S7_HANDOFF_CLOCK_MISMATCH", name, ErrorContext(module_id, (envelope.artifact_id,)))
        artifacts[name] = envelope
    return artifacts


def _unique(records: tuple[object, ...], module_id: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in records:
        candidate_id = str(getattr(item, "candidate_id"))
        if candidate_id in result:
            raise IntegrityViolation("P7_DUPLICATE_CANDIDATE_ID", candidate_id, ErrorContext(module_id, candidate_ids=(candidate_id,)))
        result[candidate_id] = item
    return result


def _decomposition_map(records: tuple[ScoreDecompositionRecord, ...]) -> dict[str, tuple[ScoreDecompositionRecord, ...]]:
    grouped: dict[str, list[ScoreDecompositionRecord]] = {}
    seen: set[tuple[str, str]] = set()
    for item in records:
        key = (item.candidate_id, item.head)
        if key in seen:
            raise IntegrityViolation("P7_DUPLICATE_SCORE_HEAD", ":".join(key), ErrorContext("P7.S8"))
        seen.add(key)
        grouped.setdefault(item.candidate_id, []).append(item)
    return {candidate_id: tuple(sorted(items, key=lambda row: row.head)) for candidate_id, items in grouped.items()}


def _scan_forbidden(value: object, forbidden: frozenset[str], path: str = "$") -> tuple[str, ...]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key) in forbidden:
                hits.append(child)
            hits.extend(_scan_forbidden(item, forbidden, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            hits.extend(_scan_forbidden(item, forbidden, f"{path}[{index}]"))
    return tuple(hits)


def _validate_partition(bundle: S8Bundle, module_id: str) -> None:
    rankable = {item.candidate_id for item in bundle.rankable}
    abstained = {item.candidate_id for item in bundle.abstained}
    blocked = {item.candidate_id for item in bundle.blocked}
    if rankable & abstained or rankable & blocked or abstained & blocked:
        raise IntegrityViolation("P7_TERMINAL_STATE_OVERLAP", "terminal states overlap", ErrorContext(module_id))
    all_ids = rankable | abstained | blocked
    if len(all_ids) != bundle.manifest_record.candidate_count:
        raise IntegrityViolation("P7_CANDIDATE_CONSERVATION_FAILED", "candidate count mismatch", ErrorContext(module_id))
    observed = sha256_value({"rankable": sorted(rankable), "abstained": sorted(abstained), "blocked": sorted(blocked)})
    if observed != bundle.manifest_record.candidate_conservation_sha256:
        raise IntegrityViolation("P7_CANDIDATE_CONSERVATION_HASH_MISMATCH", observed, ErrorContext(module_id))
    required_maps = (bundle.adjusted, bundle.clusters, bundle.groups, bundle.strategies)
    if any(not rankable.issubset(set(mapping)) for mapping in required_maps):
        raise IntegrityViolation("P7_RANKABLE_CONTEXT_MISSING", "rankable context incomplete", ErrorContext(module_id))


def load_s8_bundle(inputs: Mapping[str, object], module_id: str, forbidden_fields: tuple[str, ...]) -> S8Bundle:
    hits = _scan_forbidden(inputs, frozenset(forbidden_fields))
    if hits:
        raise TemporalViolation("P7_FUTURE_FIELD_DETECTED", ", ".join(hits[:5]), ErrorContext(module_id))
    manifest, record = _one_manifest(inputs, module_id)
    artifacts = _load_artifacts(inputs, manifest, record, module_id)
    rankable = parse_records(artifacts["rankable_candidate_panel"], RankableRecord, module_id)
    abstained = parse_records(artifacts["abstained_candidate_panel"], AbstainedRecord, module_id)
    blocked = parse_records(artifacts["final_blocked_candidate_panel"], BlockedRecord, module_id)
    group_reports = parse_records(artifacts["rankability_group_report"], GroupRankabilityRecord, module_id)
    adjusted = _unique(parse_records(artifacts["diversity_adjusted_score_panel"], DiversityAdjustedScoreRecord, module_id), module_id)
    clusters = _unique(parse_records(artifacts["candidate_diversity_cluster_panel"], DiversityClusterRecord, module_id), module_id)
    groups = _unique(parse_records(artifacts["comparison_group_panel"], ComparisonGroupRecord, module_id), module_id)
    strategies = _unique(parse_records(artifacts["validated_strategy_candidate_reference_panel"], StrategyReferenceRecord, module_id), module_id)
    decomposition = _decomposition_map(parse_records(artifacts["score_decomposition_panel"], ScoreDecompositionRecord, module_id))
    bundle = S8Bundle(manifest, record, artifacts, rankable, abstained, blocked, group_reports, adjusted, clusters, groups, strategies, decomposition)
    _validate_partition(bundle, module_id)
    return bundle
