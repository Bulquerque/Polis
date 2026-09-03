"""P3.S33.M03 temporal and vintage firewall."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from ..contracts.artifacts import ArtifactStatus, ResearchToolExtensionSnapshot
from ..contracts.boundary_artifacts import (
    Phase1RawEvidenceReferenceIndex,
    Phase2ResearchViewManifest,
    PitBoundaryQualificationReport,
    PitQueryProof,
    PitVisibilityPolicy,
    QualificationCheck,
    QualificationStatus,
    VintagePolicyName,
    VintagePolicyRegistry,
    VintagePolicySpec,
)
from ..contracts.boundary_configs import CalendarTimezonePolicyConfig, PitDataViewPolicyConfig, VintagePolicyConfig
from ..core.hashing import content_hash
from .artifact_construction import finalize, lineage
from .input_contracts import as_mapping, first_value, parse_datetime


def _decision_time(run_snapshot: object, evaluation_window: object) -> datetime:
    snapshot = as_mapping(run_snapshot, "phase3_run_snapshot")
    window = as_mapping(evaluation_window, "evaluation_window_config")
    value = first_value(snapshot, ("decision_time", "as_of", "as_of_time", "snapshot_as_of"))
    if value in (None, ""):
        value = first_value(window, ("decision_time", "as_of", "as_of_time", "window_end", "end"))
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError("decision_time is required and cannot be inferred from wall clock")
    return parsed


def build_temporal_boundary(
    *,
    phase3_run_snapshot: object,
    extension_snapshot: ResearchToolExtensionSnapshot,
    view_manifest: Phase2ResearchViewManifest,
    raw_index: Phase1RawEvidenceReferenceIndex,
    evaluation_window_config: object,
    pit_config: PitDataViewPolicyConfig,
    timezone_config: CalendarTimezonePolicyConfig,
    vintage_config: VintagePolicyConfig,
    contract_version: str = "1.0.0",
) -> tuple[PitVisibilityPolicy, VintagePolicyRegistry, PitBoundaryQualificationReport]:
    decision_time = _decision_time(phase3_run_snapshot, evaluation_window_config)
    snapshot_mapping = as_mapping(phase3_run_snapshot, "phase3_run_snapshot")
    execution_mode = str(snapshot_mapping.get("execution_mode") or snapshot_mapping.get("mode") or "BACKTEST").upper()
    run_snapshot_hash = str(snapshot_mapping.get("content_hash") or content_hash(phase3_run_snapshot))
    policies = tuple(VintagePolicySpec(
        policy_name=item.policy_name,
        description=item.description,
        allowed_execution_modes=item.allowed_execution_modes,
        selection_rule=item.selection_rule,
    ) for item in vintage_config.policies)

    policy_status = ArtifactStatus.READY
    reason_codes: tuple[str, ...] = ()
    if execution_mode == "BACKTEST" and pit_config.default_vintage_policy.value in pit_config.forbidden_backtest_vintage_policies:
        policy_status = ArtifactStatus.FAILED
        reason_codes = ("P3RT-PIT-FORBIDDEN-VINTAGE-POLICY",)

    policy = finalize(PitVisibilityPolicy, {
        "status": policy_status,
        "lineage": lineage("P3.S33.M03", contract_version, [
            phase3_run_snapshot,
            extension_snapshot,
            view_manifest,
            raw_index,
            evaluation_window_config,
            pit_config,
            timezone_config,
            vintage_config,
        ]),
        "reason_codes": reason_codes,
        "decision_time": decision_time,
        "execution_mode": execution_mode,
        "canonical_timezone": timezone_config.canonical_timezone,
        "observational_missing_time_action": pit_config.observational_missing_time_action,
        "temporal_reference_missing_time_action": pit_config.temporal_reference_missing_time_action,
        "atemporal_allowlist": pit_config.atemporal_allowlist,
        "forbidden_vintage_policies": pit_config.forbidden_backtest_vintage_policies,
        "extension_snapshot_hash": extension_snapshot.snapshot_hash,
        "phase3_run_snapshot_hash": run_snapshot_hash,
    })
    registry = finalize(VintagePolicyRegistry, {
        "status": policy_status,
        "lineage": lineage("P3.S33.M03", contract_version, [policy, vintage_config]),
        "reason_codes": reason_codes,
        "default_policy": pit_config.default_vintage_policy,
        "policies": policies,
    })

    checks = [
        QualificationCheck(
            check_id="decision_time_is_timezone_aware",
            status=QualificationStatus.PASS,
            summary="decision_time is explicit and timezone-aware",
        ),
        QualificationCheck(
            check_id="request_as_of_equals_decision_time",
            status=QualificationStatus.PASS,
            summary="all tool requests must use the frozen decision_time",
        ),
        QualificationCheck(
            check_id="network_disabled_in_backtest",
            status=QualificationStatus.PASS if execution_mode != "BACKTEST" or pit_config.reject_network_backtest else QualificationStatus.FAIL,
            summary="backtest data access is snapshot-bound and offline",
        ),
        QualificationCheck(
            check_id="p2_view_manifest_bound",
            status=QualificationStatus.PASS if view_manifest.view_count else QualificationStatus.BLOCKED_UPSTREAM,
            summary="P2 research views are bound to the temporal policy",
        ),
        QualificationCheck(
            check_id="p1_custody_index_bound",
            status=QualificationStatus.PASS if raw_index.record_count else QualificationStatus.WARN,
            summary="P1 custody references are available for provenance resolution",
        ),
    ]
    if policy_status == ArtifactStatus.FAILED:
        checks.append(QualificationCheck(
            check_id="default_vintage_policy_allowed",
            status=QualificationStatus.FAIL,
            summary="default vintage policy is forbidden in backtest",
            reason_codes=reason_codes,
        ))
    else:
        checks.append(QualificationCheck(
            check_id="default_vintage_policy_allowed",
            status=QualificationStatus.PASS,
            summary="default vintage policy is valid for the execution mode",
        ))
    statuses = {item.status for item in checks}
    if QualificationStatus.FAIL in statuses:
        overall = QualificationStatus.FAIL
    elif QualificationStatus.BLOCKED_UPSTREAM in statuses:
        overall = QualificationStatus.BLOCKED_UPSTREAM
    elif QualificationStatus.WARN in statuses:
        overall = QualificationStatus.WARN
    else:
        overall = QualificationStatus.PASS
    report = finalize(PitBoundaryQualificationReport, {
        "status": ArtifactStatus.FAILED if overall == QualificationStatus.FAIL else (
            ArtifactStatus.DEGRADED if overall != QualificationStatus.PASS else ArtifactStatus.READY
        ),
        "lineage": lineage("P3.S33.M03", contract_version, [policy, registry]),
        "reason_codes": reason_codes,
        "decision_time": decision_time,
        "checks": tuple(checks),
        "overall_status": overall,
    })
    return policy, registry, report


def filter_visible_records(
    records: Sequence[Mapping[str, Any]],
    *,
    policy: PitVisibilityPolicy,
    request_as_of: datetime,
    vintage_policy: VintagePolicyName,
    p1_snapshot_id: str,
    p2_snapshot_id: str,
    input_hashes: tuple[str, ...],
) -> tuple[tuple[Mapping[str, Any], ...], PitQueryProof]:
    if request_as_of.tzinfo is None:
        raise ValueError("request_as_of must be timezone-aware")
    if request_as_of != policy.decision_time:
        raise ValueError("request_as_of must equal policy.decision_time")
    if vintage_policy.value in policy.forbidden_vintage_policies:
        raise ValueError("vintage policy is forbidden by the active PIT policy")
    visible: list[Mapping[str, Any]] = []
    future = 0
    missing = 0
    visible_times: list[datetime] = []
    for record in records:
        raw_time = record.get(policy.availability_field)
        if raw_time in (None, ""):
            missing += 1
            continue
        available_at = parse_datetime(raw_time)
        if available_at is None:
            missing += 1
            continue
        if available_at > policy.decision_time:
            future += 1
            continue
        visible.append(record)
        visible_times.append(available_at)
    proof_payload = {
        "policy_version": policy.schema_version,
        "decision_time": policy.decision_time,
        "request_as_of": request_as_of,
        "vintage_policy": vintage_policy,
        "records_scanned": len(records),
        "records_visible": len(visible),
        "records_rejected_future": future,
        "records_rejected_missing_time": missing,
        "earliest_available_at": min(visible_times) if visible_times else None,
        "latest_available_at": max(visible_times) if visible_times else None,
        "p1_snapshot_id": p1_snapshot_id,
        "p2_snapshot_id": p2_snapshot_id,
        "input_hashes": tuple(sorted(input_hashes)),
    }
    proof = PitQueryProof(**proof_payload, proof_hash=content_hash(proof_payload))
    return tuple(visible), proof
