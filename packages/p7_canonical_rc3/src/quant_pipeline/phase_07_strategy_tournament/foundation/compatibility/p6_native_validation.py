"""Validation of native P6 RC6.1 artifacts before P7 normalization."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..errors import P7S1Error
from ..reason_codes import ReasonCode
from .p6_native_hashing import canonical_sha256, p6_wire_sha256

MODULE_ID = "P7.S1.P6_NATIVE_ADAPTER"
P6_MANIFEST = "phase7_strategy_handoff_manifest"
ARTIFACT_TYPE_ALIASES = {"candidate_equivalence_panel_final": "candidate_equivalence_panel"}
P7_REQUIRED = (
    "strategy_candidate_panel", "strategy_leg_panel", "strategy_market_snapshot",
    "strategy_payoff_panel", "strategy_scenario_evaluation_panel", "strategy_risk_panel",
    "strategy_cost_liquidity_panel", "strategy_lineage_panel",
    "strategy_generation_trace_panel", "candidate_rejection_report",
    "candidate_generation_audit",
)
P7_OPTIONAL = (
    "strategy_ambiguity_evaluation_panel", "strategy_greek_panel",
    "candidate_equivalence_panel", "p5_handoff_compatibility_report",
    "strategy_qualification_panel",
    "candidate_feature_base_panel",
)


@dataclass(frozen=True, slots=True)
class NativeP6Bundle:
    manifest_envelope: dict[str, Any]
    manifest_record: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]
    ignored_artifact_names: tuple[str, ...]


def is_native_p6_manifest(value: Mapping[str, Any]) -> bool:
    return value.get("artifact_type") == P6_MANIFEST and isinstance(value.get("records"), list)


def validate_native_bundle(
    manifest_payload: Mapping[str, Any], artifact_payloads: Sequence[Mapping[str, Any]]
) -> NativeP6Bundle:
    manifest = _validated_envelope(manifest_payload, expected_type=P6_MANIFEST)
    records = manifest["records"]
    if len(records) != 1 or not isinstance(records[0], Mapping):
        _fail("native P6 manifest must contain exactly one record")
    record = dict(records[0])
    if record.get("target_phase") != "P7":
        _fail("native P6 manifest has the wrong target phase")
    supplied = _unique_artifacts(artifact_payloads)
    references = _references(record)
    missing = sorted(set(P7_REQUIRED) - set(references))
    if missing:
        _fail("native P6 manifest misses required P7 artifacts", {"missing": missing})
    selected_names = set(P7_REQUIRED) | (set(P7_OPTIONAL) & set(references))
    missing_payloads = sorted(selected_names - set(supplied))
    if missing_payloads:
        _fail("native P6 artifacts declared for P7 were not supplied", {"missing": missing_payloads})
    selected: dict[str, dict[str, Any]] = {}
    for name in sorted(selected_names):
        artifact = _validated_envelope(supplied[name], expected_type=name, allow_alias=True)
        _validate_reference(artifact, references[name])
        _validate_identity(artifact, manifest, record)
        selected[name] = artifact
    _validate_candidate_identity(record, selected["strategy_candidate_panel"])
    ignored = tuple(sorted(set(supplied) - selected_names))
    return NativeP6Bundle(manifest, record, selected, ignored)


def _validated_envelope(
    payload: Mapping[str, Any], *, expected_type: str, allow_alias: bool = False
) -> dict[str, Any]:
    artifact = dict(payload)
    actual_type = artifact.get("artifact_type")
    normalized_type = ARTIFACT_TYPE_ALIASES.get(str(actual_type), actual_type) if allow_alias else actual_type
    if normalized_type != expected_type:
        _fail("native P6 artifact type mismatch", {"expected": expected_type, "actual": actual_type})
    records = artifact.get("records")
    if not isinstance(records, list):
        _fail("native P6 artifact records must be a list", {"artifact": expected_type})
    if artifact.get("record_count") != len(records):
        _fail("native P6 artifact record count mismatch", {"artifact": expected_type})
    if p6_wire_sha256(records) != artifact.get("content_sha256"):
        _fail("native P6 artifact hash mismatch", {"artifact": expected_type})
    for field in ("run_id", "cycle_id", "decision_time", "created_at", "available_at", "artifact_id"):
        if not artifact.get(field):
            _fail("native P6 artifact identity is incomplete", {"artifact": expected_type, "field": field})
    _parse_time(str(artifact["decision_time"]))
    _parse_time(str(artifact["created_at"]))
    _parse_time(str(artifact["available_at"]))
    return artifact


def _unique_artifacts(values: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        raw_name = value.get("artifact_type")
        name = ARTIFACT_TYPE_ALIASES.get(str(raw_name), raw_name)
        if not isinstance(name, str) or not name:
            _fail("native P6 artifact is missing artifact_type")
        if name in result:
            _fail("native P6 artifact types must be unique", {"artifact": name})
        result[name] = dict(value)
    return result


def _references(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = record.get("artifact_references")
    if not isinstance(rows, list):
        _fail("native P6 manifest references must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("artifact_type"), str):
            _fail("native P6 manifest contains an invalid artifact reference")
        name = str(row["artifact_type"])
        if name in result:
            _fail("native P6 manifest artifact references must be unique", {"artifact": name})
        result[name] = dict(row)
    return result


def _validate_reference(artifact: Mapping[str, Any], reference: Mapping[str, Any]) -> None:
    fields = ("artifact_id", "content_sha256", "record_count", "schema_version")
    mismatches = {field: [artifact.get(field), reference.get(field)] for field in fields
                  if artifact.get(field) != reference.get(field)}
    if mismatches:
        _fail("native P6 artifact does not match its manifest reference", {
            "artifact": artifact.get("artifact_type"), "mismatches": mismatches,
        })


def _validate_identity(
    artifact: Mapping[str, Any], manifest: Mapping[str, Any], record: Mapping[str, Any]
) -> None:
    expected = {
        "run_id": manifest.get("run_id"), "cycle_id": record.get("cycle_id"),
        "decision_time": record.get("decision_time"),
    }
    mismatches = {field: [artifact.get(field), wanted] for field, wanted in expected.items()
                  if artifact.get(field) != wanted}
    if mismatches:
        _fail("native P6 artifact identity conflicts with the handoff", {
            "artifact": artifact.get("artifact_type"), "mismatches": mismatches,
        })


def _validate_candidate_identity(record: Mapping[str, Any], candidate_artifact: Mapping[str, Any]) -> None:
    candidate_ids = sorted(str(row.get("candidate_id")) for row in candidate_artifact["records"])
    if record.get("candidate_count") != len(candidate_ids):
        _fail("native P6 manifest candidate count mismatch")
    if canonical_sha256(candidate_ids) != record.get("candidate_ids_sha256"):
        _fail("native P6 manifest candidate identity hash mismatch")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _fail(message: str, details: Mapping[str, Any] | None = None) -> None:
    raise P7S1Error(ReasonCode.P6_MANIFEST_INVALID, message, MODULE_ID, dict(details or {}))
