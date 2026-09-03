from __future__ import annotations

from collections import defaultdict
from typing import Any

from .artifacts import ArtifactEnvelope
from .records import S9Policy


def selected_family_counts(matrix: ArtifactEnvelope) -> dict[str, int]:
    catalog = matrix.metadata.get("feature_catalog", {})
    counts: dict[str, set[str]] = defaultdict(set)
    for descriptor in catalog.values():
        family_id = str(descriptor.get("family_id") or "UNASSIGNED")
        feature_id = str(descriptor.get("feature_id") or "")
        if feature_id:
            counts[family_id].add(feature_id)
    return {family_id: len(features) for family_id, features in counts.items()}


def _severity_index(value: str) -> int:
    return {"INSUFFICIENT_DATA": -1, "PASS": 0, "WARN": 1, "BLOCK": 2}[value]


def _group_drift(
    drift_records: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], list[str]]:
    by_family: dict[str, list[str]] = defaultdict(list)
    by_representation: list[str] = []
    for record in drift_records:
        severity = str(record["severity"])
        family = str(record.get("family_id") or "UNASSIGNED")
        by_family[family].append(severity)
        if record["scope_type"] == "REPRESENTATION":
            by_representation.append(severity)
    return by_family, by_representation


def _family_gate_record(
    *,
    family: str,
    severities: list[str],
    selected_count: int,
    minimum: int,
    required: bool,
    strict: bool,
) -> tuple[dict[str, Any], bool]:
    coverage_missing = selected_count < minimum
    reasons = sorted(set(severities) - {"PASS", "INSUFFICIENT_DATA"})
    if coverage_missing:
        reasons.append("FAMILY_COVERAGE_BELOW_POLICY")
    if "BLOCK" in severities or (coverage_missing and required and strict):
        decision = "BLOCK_FAMILY"
    elif "WARN" in severities or coverage_missing:
        decision = "PASS_WITH_DEGRADATION"
    else:
        decision = "PASS"
    record = {
        "gate_scope": "FAMILY",
        "scope_id": family,
        "decision": decision,
        "block_count": severities.count("BLOCK")
        + int(coverage_missing and required and strict),
        "warn_count": severities.count("WARN")
        + int(coverage_missing and not strict),
        "reason_codes": sorted(set(reasons)),
        "selected_feature_count": selected_count,
        "minimum_required_features": minimum,
    }
    return record, coverage_missing


def _expected_family_records(
    *,
    by_family: dict[str, list[str]],
    family_counts: dict[str, int],
    policy: S9Policy,
) -> tuple[list[dict[str, Any]], list[str]]:
    expected = tuple(policy.family_coverage.expected_family_ids)
    required = set(policy.family_coverage.required_family_ids)
    minimum = policy.family_coverage.min_selected_features_per_family
    strict = policy.family_coverage.strict_complete_handoff
    records: list[dict[str, Any]] = []
    coverage_failures: list[str] = []
    for family in expected:
        record, missing = _family_gate_record(
            family=family,
            severities=by_family.get(family, []),
            selected_count=family_counts.get(family, 0),
            minimum=minimum,
            required=family in required,
            strict=strict,
        )
        records.append(record)
        if missing:
            coverage_failures.append(family)
    return records, coverage_failures


def _unregistered_family_records(
    *,
    by_family: dict[str, list[str]],
    expected: set[str],
    registered: set[str],
    family_counts: dict[str, int],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for family in sorted(set(by_family) - registered):
        severities = by_family[family]
        decision = (
            "BLOCK_FAMILY"
            if "BLOCK" in severities
            else "PASS_WITH_DEGRADATION"
            if "WARN" in severities
            else "PASS"
        )
        records.append(
            {
                "gate_scope": "FAMILY",
                "scope_id": family,
                "decision": decision,
                "block_count": severities.count("BLOCK"),
                "warn_count": severities.count("WARN"),
                "reason_codes": ["UNREGISTERED_FAMILY"],
                "selected_feature_count": family_counts.get(family, 0),
                "minimum_required_features": 0,
            }
        )
    return records


def _representation_record(severities: list[str]) -> dict[str, Any]:
    highest = max(severities or ["PASS"], key=_severity_index)
    decision = {
        "BLOCK": "BLOCK_REPRESENTATION",
        "WARN": "PASS_WITH_DEGRADATION",
    }.get(highest, "PASS")
    return {
        "gate_scope": "REPRESENTATION",
        "scope_id": "ALL",
        "decision": decision,
        "block_count": severities.count("BLOCK"),
        "warn_count": severities.count("WARN"),
        "reason_codes": [],
        "selected_feature_count": 0,
        "minimum_required_features": 0,
    }


def _final_decision(
    *,
    block_count: int,
    warn_count: int,
    missing_required: list[str],
    policy: S9Policy,
) -> str:
    if block_count > policy.max_block_records_before_handoff_block:
        return "BLOCK_HANDOFF"
    if missing_required and policy.family_coverage.strict_complete_handoff:
        return "BLOCK_HANDOFF"
    if missing_required:
        return "PARTIAL_HANDOFF"
    if warn_count > policy.max_warn_records_before_degradation:
        return "PASS_WITH_DEGRADATION"
    return "PASS"


def _handoff_record(
    *,
    final: str,
    block_count: int,
    warn_count: int,
    missing_required: list[str],
    selected_count: int,
    minimum_required: int,
    strict: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    if missing_required:
        reasons.append("REQUIRED_FAMILY_COVERAGE_INCOMPLETE")
    if block_count:
        reasons.append("DRIFT_BLOCK_PRESENT")
    if warn_count:
        reasons.append("DRIFT_WARNING_PRESENT")
    return {
        "gate_scope": "HANDOFF",
        "scope_id": "P4_TO_P5",
        "decision": final,
        "block_count": block_count + int(bool(missing_required) and strict),
        "warn_count": warn_count + int(bool(missing_required) and not strict),
        "reason_codes": reasons,
        "selected_feature_count": selected_count,
        "minimum_required_features": minimum_required,
    }


def _gate_summary(
    expected: tuple[str, ...],
    registered: set[str],
    required: set[str],
    family_counts: dict[str, int],
    missing_required: list[str],
    strict: bool,
) -> dict[str, Any]:
    return {
        "expected_family_ids": list(expected),
        "registered_family_ids": sorted(registered),
        "required_family_ids": sorted(required),
        "selected_features_by_family": dict(sorted(family_counts.items())),
        "missing_required_family_ids": missing_required,
        "completeness_status": (
            "COMPLETE"
            if not missing_required
            else "BLOCKED"
            if strict
            else "PARTIAL"
        ),
    }


def build_gate_records(
    drift_records: list[dict[str, Any]],
    matrix: ArtifactEnvelope,
    policy: S9Policy,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    by_family, by_representation = _group_drift(drift_records)
    family_counts = selected_family_counts(matrix)
    expected = tuple(policy.family_coverage.expected_family_ids)
    registered = set(policy.family_coverage.registered_family_ids) or set(expected)
    required = set(policy.family_coverage.required_family_ids)
    minimum = policy.family_coverage.min_selected_features_per_family
    strict = policy.family_coverage.strict_complete_handoff

    records, coverage_failures = _expected_family_records(
        by_family=by_family,
        family_counts=family_counts,
        policy=policy,
    )
    records.extend(
        _unregistered_family_records(
            by_family=by_family,
            expected=set(expected),
            registered=registered,
            family_counts=family_counts,
        )
    )
    records.append(_representation_record(by_representation))

    block_count = sum(item["severity"] == "BLOCK" for item in drift_records)
    warn_count = sum(item["severity"] == "WARN" for item in drift_records)
    missing_required = sorted(set(coverage_failures) & required)
    final = _final_decision(
        block_count=block_count,
        warn_count=warn_count,
        missing_required=missing_required,
        policy=policy,
    )
    records.append(
        _handoff_record(
            final=final,
            block_count=block_count,
            warn_count=warn_count,
            missing_required=missing_required,
            selected_count=sum(family_counts.values()),
            minimum_required=minimum * len(required),
            strict=strict,
        )
    )
    summary = _gate_summary(
        expected=expected,
        registered=registered,
        required=required,
        family_counts=family_counts,
        missing_required=missing_required,
        strict=strict,
    )
    return records, final, summary
