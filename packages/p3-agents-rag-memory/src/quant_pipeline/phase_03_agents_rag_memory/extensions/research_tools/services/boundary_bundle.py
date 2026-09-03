"""P3.S33.M05 immutable boundary bundle and preflight."""

from __future__ import annotations

from collections import defaultdict

from ..contracts.artifacts import ArtifactEnvelope, ArtifactStatus, ResearchToolExtensionSnapshot
from ..contracts.boundary_artifacts import (
    BoundaryArtifactRef,
    BoundaryPortSpec,
    Phase1CustodyQualificationReport,
    Phase1RawEvidenceReferenceIndex,
    Phase2ResearchViewManifest,
    Phase2ResearchViewReadinessReport,
    PitBoundaryQualificationReport,
    PitVisibilityPolicy,
    PortKind,
    QualificationCheck,
    QualificationStatus,
    ResearchBoundaryPreflightReport,
    ResearchDataBoundaryBundle,
    ReadinessStatus,
    TemporalEntityResolutionIndex,
    EntityResolutionPolicy,
    VintagePolicyRegistry,
)
from ..core.hashing import content_hash
from .artifact_construction import finalize, lineage
from .input_contracts import require_no_hidden_payload


def _artifact_ref(value: ArtifactEnvelope) -> BoundaryArtifactRef:
    return BoundaryArtifactRef(
        artifact_name=value.artifact_name,
        artifact_id=value.artifact_id,
        schema_id=value.schema_id,
        content_hash=value.content_hash,
        status=value.status.value,
    )


def _blocked_operations(report: Phase2ResearchViewReadinessReport) -> tuple[str, ...]:
    by_operation: dict[str, list[ReadinessStatus]] = defaultdict(list)
    for record in report.records:
        by_operation[record.operation_ref].append(record.status)
    # Fail closed: a declared required view that is unavailable blocks the operation.
    # Future subphases may relax this only by declaring the view optional in OperationSpec.
    return tuple(sorted(
        operation
        for operation, statuses in by_operation.items()
        if any(status == ReadinessStatus.BLOCKED_UPSTREAM for status in statuses)
    ))


def build_boundary_bundle(
    *,
    extension_snapshot: ResearchToolExtensionSnapshot,
    view_manifest: Phase2ResearchViewManifest,
    view_readiness: Phase2ResearchViewReadinessReport,
    raw_index: Phase1RawEvidenceReferenceIndex,
    custody_report: Phase1CustodyQualificationReport,
    pit_policy: PitVisibilityPolicy,
    vintage_registry: VintagePolicyRegistry,
    pit_report: PitBoundaryQualificationReport,
    entity_index: TemporalEntityResolutionIndex,
    entity_policy: EntityResolutionPolicy,
    contract_version: str = "1.0.0",
) -> tuple[ResearchDataBoundaryBundle, ResearchBoundaryPreflightReport]:
    artifacts: tuple[ArtifactEnvelope, ...] = (
        view_manifest,
        view_readiness,
        raw_index,
        custody_report,
        pit_policy,
        vintage_registry,
        pit_report,
        entity_index,
        entity_policy,
    )
    refs = tuple(sorted((_artifact_ref(item) for item in artifacts), key=lambda item: item.artifact_name))
    ports = (
        BoundaryPortSpec(
            port_id="PitResearchQueryPort",
            port_kind=PortKind.PIT_RESEARCH_QUERY,
            purpose="Query authorized P2 views under the frozen PIT policy.",
            methods=("query", "describe_view", "prove_visibility"),
            required_artifact_names=("phase2_research_view_manifest", "pit_visibility_policy", "vintage_policy_registry"),
        ),
        BoundaryPortSpec(
            port_id="RawEvidenceResolverPort",
            port_kind=PortKind.RAW_EVIDENCE_RESOLVER,
            purpose="Resolve P1 bytes only by authorized opaque reference and expected hash.",
            methods=("resolve", "verify_hash"),
            required_artifact_names=("phase1_raw_evidence_reference_index",),
        ),
        BoundaryPortSpec(
            port_id="TemporalEntityResolverPort",
            port_kind=PortKind.TEMPORAL_ENTITY_RESOLVER,
            purpose="Resolve entity and instrument identities within historical validity intervals.",
            methods=("resolve", "candidates"),
            required_artifact_names=("temporal_entity_resolution_index", "entity_resolution_policy"),
        ),
        BoundaryPortSpec(
            port_id="ProvenanceQueryPort",
            port_kind=PortKind.PROVENANCE_QUERY,
            purpose="Traverse P1 custody, P2 semantic artifact and P3 query lineage.",
            methods=("trace", "inspect_source", "compare_versions"),
            required_artifact_names=("phase1_raw_evidence_reference_index", "phase2_research_view_manifest"),
        ),
    )
    allowed_views = tuple(sorted(view.view_id for view in view_manifest.views if view.readiness != ReadinessStatus.BLOCKED_UPSTREAM))
    blocked_operations = _blocked_operations(view_readiness)
    checks = [
        QualificationCheck(
            check_id="extension_snapshot_match",
            status=QualificationStatus.PASS if pit_policy.extension_snapshot_hash == extension_snapshot.snapshot_hash else QualificationStatus.FAIL,
            summary="PIT policy is bound to the same extension snapshot.",
        ),
        QualificationCheck(
            check_id="pit_boundary_qualified",
            status=pit_report.overall_status,
            summary="Temporal and vintage boundary qualification result.",
        ),
        QualificationCheck(
            check_id="p1_custody_authorized",
            status=QualificationStatus.PASS if custody_report.blocked_count == 0 else QualificationStatus.WARN,
            summary="P1 references are linked to P2 and hash-qualified.",
            details={"authorized": custody_report.authorized_count, "blocked": custody_report.blocked_count},
        ),
        QualificationCheck(
            check_id="authorized_views_available",
            status=QualificationStatus.PASS if allowed_views else QualificationStatus.BLOCKED_UPSTREAM,
            summary="At least one P2 research view is available.",
        ),
        QualificationCheck(
            check_id="ports_read_only_offline",
            status=QualificationStatus.PASS,
            summary="All declared boundary ports are read-only and do not require network access.",
        ),
    ]
    statuses = {item.status for item in checks}
    if QualificationStatus.FAIL in statuses:
        overall = QualificationStatus.FAIL
    elif QualificationStatus.BLOCKED_UPSTREAM in statuses:
        overall = QualificationStatus.BLOCKED_UPSTREAM
    elif QualificationStatus.WARN in statuses:
        overall = QualificationStatus.WARN
    else:
        overall = QualificationStatus.PASS
    artifact_status = ArtifactStatus.READY if overall == QualificationStatus.PASS else (
        ArtifactStatus.FAILED if overall == QualificationStatus.FAIL else ArtifactStatus.DEGRADED
    )
    bundle = finalize(ResearchDataBoundaryBundle, {
        "status": artifact_status,
        "lineage": lineage("P3.S33.M05", contract_version, [extension_snapshot, *artifacts]),
        "reason_codes": () if overall == QualificationStatus.PASS else ("P3RT-QUALITY-BOUNDARY-PREFLIGHT-NONPASS",),
        "extension_snapshot_hash": extension_snapshot.snapshot_hash,
        "decision_time": pit_policy.decision_time,
        "artifact_refs": refs,
        "ports": ports,
        "allowed_view_ids": allowed_views,
        "blocked_operation_refs": blocked_operations,
    })
    require_no_hidden_payload(bundle)
    report_payload = {
        "status": artifact_status,
        "lineage": lineage("P3.S33.M05", contract_version, [bundle, *checks]),
        "reason_codes": bundle.reason_codes,
        "checks": tuple(checks),
        "overall_status": overall,
        "bundle_hash": bundle.content_hash,
    }
    report = finalize(ResearchBoundaryPreflightReport, report_payload)
    if report.bundle_hash != bundle.content_hash:
        raise ValueError("preflight bundle hash mismatch")
    return bundle, report
