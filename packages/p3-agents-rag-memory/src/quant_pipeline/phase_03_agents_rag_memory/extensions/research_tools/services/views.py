"""P3.S33.M01 phase-two research view authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts.artifacts import ArtifactStatus, CanonicalToolOperationRegistry
from ..contracts.boundary_artifacts import (
    Phase2ResearchViewManifest,
    Phase2ResearchViewReadinessReport,
    Phase2ResearchViewRecord,
    QualityStatus,
    ReadinessStatus,
    ViewClass,
    ViewOperationReadinessRecord,
)
from ..core.hashing import content_hash, stable_artifact_id
from .artifact_construction import finalize, lineage
from .input_contracts import as_mapping, as_records, metadata_without_payload, unique_strings


@dataclass(frozen=True, slots=True)
class ViewDefinition:
    artifact_name: str
    view_class: ViewClass
    availability_field: str
    entity_key_fields: tuple[str, ...]
    temporal_grain: tuple[str, ...]


VIEW_DEFINITIONS = (
    ViewDefinition("clean_context_source_panel", ViewClass.REFERENCE, "available_at", ("source_id",), ("source_id", "available_at")),
    ViewDefinition("clean_document_panel", ViewClass.DOCUMENTARY, "available_at", ("document_id", "entity_id"), ("document_id", "available_at")),
    ViewDefinition("clean_event_reference_panel", ViewClass.DOCUMENTARY, "available_at", ("event_id", "entity_id"), ("event_id", "available_at")),
    ViewDefinition("source_quality_panel", ViewClass.REFERENCE, "available_at", ("source_id",), ("source_id", "available_at")),
    ViewDefinition("clean_underlying_panel", ViewClass.MARKET, "available_at", ("underlying",), ("date", "underlying")),
    ViewDefinition("clean_underlying_trade_panel", ViewClass.MARKET, "available_at", ("underlying", "trade_id"), ("available_at", "underlying", "trade_id")),
    ViewDefinition("clean_benchmark_panel", ViewClass.MARKET, "available_at", ("benchmark_id",), ("date", "benchmark_id")),
    ViewDefinition("clean_calendar_panel", ViewClass.REFERENCE, "available_at", ("calendar_id",), ("date", "calendar_id")),
    ViewDefinition("clean_corporate_actions_panel", ViewClass.MARKET, "available_at", ("underlying", "action_id"), ("underlying", "announcement_date", "action_id")),
    ViewDefinition("clean_macro_br_panel", ViewClass.MACRO, "available_at", ("series_id",), ("reference_date", "series_id")),
    ViewDefinition("clean_macro_us_panel", ViewClass.MACRO, "available_at", ("series_id",), ("reference_date", "series_id")),
    ViewDefinition("clean_option_contract_panel", ViewClass.OPTIONS, "available_at", ("contract_id", "underlying"), ("contract_id", "available_at")),
    ViewDefinition("clean_option_quotes_panel", ViewClass.OPTIONS, "available_at", ("contract_id",), ("contract_id", "available_at")),
    ViewDefinition("clean_cost_reference_panel", ViewClass.REFERENCE, "available_at", ("cost_id", "underlying"), ("cost_id", "available_at")),
    ViewDefinition("clean_liquidity_reference_panel", ViewClass.MARKET, "available_at", ("underlying",), ("underlying", "available_at")),
)


def _quality_status(report: object) -> QualityStatus:
    if not isinstance(report, dict):
        try:
            report = dict(report)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return QualityStatus.UNKNOWN
    raw = str(report.get("status") or "LEGACY_UNVERIFIED").upper()
    return QualityStatus(raw) if raw in QualityStatus._value2member_map_ else QualityStatus.UNKNOWN


def _handoff_routes(handoffs: dict[str, object]) -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for handoff_name, value in handoffs.items():
        try:
            raw = as_mapping(value, handoff_name)
        except TypeError:
            continue
        refs = raw.get("artifact_refs")
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict) and ref.get("artifact_name"):
                    routes.setdefault(str(ref["artifact_name"]), set()).add(handoff_name)
    return routes


def _operation_refs(registry: CanonicalToolOperationRegistry, view_class: ViewClass) -> tuple[str, ...]:
    refs = {
        f"{operation.tool_id}/{operation.operation_id}"
        for operation in registry.operations
        if view_class.value in operation.required_view_classes
    }
    return tuple(sorted(refs))


def build_phase2_views(
    *,
    inputs: dict[str, Any],
    operation_registry: CanonicalToolOperationRegistry,
    extension_snapshot_hash: str,
    contract_version: str = "1.0.0",
) -> tuple[Phase2ResearchViewManifest, Phase2ResearchViewReadinessReport]:
    quality = _quality_status(inputs.get("quality_report_phase_2"))
    routes = _handoff_routes({
        "phase3_handoff_manifest": inputs.get("phase3_handoff_manifest"),
        "phase4_handoff_manifest": inputs.get("phase4_handoff_manifest"),
        "phase6_handoff_manifest": inputs.get("phase6_handoff_manifest"),
    })
    view_records: list[Phase2ResearchViewRecord] = []
    readiness_records: list[ViewOperationReadinessRecord] = []

    for definition in VIEW_DEFINITIONS:
        view_id = f"p2.{definition.artifact_name}.v1"
        operation_refs = _operation_refs(operation_registry, definition.view_class)
        artifact = inputs.get(definition.artifact_name)
        if artifact is None:
            for operation_ref in operation_refs:
                readiness_records.append(ViewOperationReadinessRecord(
                    view_id=view_id,
                    operation_ref=operation_ref,
                    status=ReadinessStatus.BLOCKED_UPSTREAM,
                    reason_codes=("P3RT-UPSTREAM-P2-VIEW-MISSING",),
                ))
            continue

        raw = as_mapping(artifact, definition.artifact_name)
        rows = as_records(artifact)
        artifact_hash = str(raw.get("content_hash") or content_hash(artifact))
        artifact_id = str(raw.get("artifact_id") or stable_artifact_id(definition.artifact_name, artifact_hash))
        lineage_ids = set(unique_strings(rows, ("lineage_id",)))
        if raw.get("lineage_id"):
            lineage_ids.add(str(raw["lineage_id"]))
        source_ids = unique_strings(rows, ("source_id", "provider_id"))
        reason_codes: tuple[str, ...] = ()
        if quality == QualityStatus.BLOCK:
            readiness = ReadinessStatus.BLOCKED_UPSTREAM
            reason_codes = ("P3RT-UPSTREAM-P2-QUALITY-BLOCK",)
        elif quality in {QualityStatus.WARN, QualityStatus.DEGRADED, QualityStatus.LEGACY_UNVERIFIED, QualityStatus.UNKNOWN}:
            readiness = ReadinessStatus.DEGRADED
            reason_codes = ("P3RT-QUALITY-P2-NONPASS",)
        else:
            readiness = ReadinessStatus.READY

        view_records.append(Phase2ResearchViewRecord(
            view_id=view_id,
            view_class=definition.view_class,
            artifact_name=definition.artifact_name,
            artifact_id=artifact_id,
            schema_version=str(raw.get("schema_version") or raw.get("pipeline_version") or "unknown"),
            content_hash=artifact_hash,
            lineage_ids=tuple(sorted(lineage_ids)),
            availability_field=definition.availability_field,
            entity_key_fields=definition.entity_key_fields,
            temporal_grain=definition.temporal_grain,
            allowed_operation_refs=operation_refs,
            quality_status=quality,
            readiness=readiness,
            record_count=len(rows),
            source_ids=source_ids,
            routed_by_handoffs=tuple(sorted(routes.get(definition.artifact_name, set()))),
            storage_metadata_hash=content_hash(metadata_without_payload(artifact)),
            reason_codes=reason_codes,
        ))
        for operation_ref in operation_refs:
            readiness_records.append(ViewOperationReadinessRecord(
                view_id=view_id,
                operation_ref=operation_ref,
                status=readiness,
                reason_codes=reason_codes,
            ))

    view_records.sort(key=lambda item: item.view_id)
    readiness_records.sort(key=lambda item: (item.operation_ref, item.view_id))
    status = ArtifactStatus.READY
    if any(record.readiness != ReadinessStatus.READY for record in view_records) or len(view_records) != len(VIEW_DEFINITIONS):
        status = ArtifactStatus.DEGRADED

    source_inputs = [inputs.get(item.artifact_name) for item in VIEW_DEFINITIONS if inputs.get(item.artifact_name) is not None]
    manifest = finalize(Phase2ResearchViewManifest, {
        "status": status,
        "lineage": lineage("P3.S33.M01", contract_version, [operation_registry, *source_inputs]),
        "reason_codes": () if status == ArtifactStatus.READY else ("P3RT-UPSTREAM-P2-PARTIAL-READINESS",),
        "extension_snapshot_hash": extension_snapshot_hash,
        "views": tuple(view_records),
        "view_count": len(view_records),
    })
    report = finalize(Phase2ResearchViewReadinessReport, {
        "status": status,
        "lineage": lineage("P3.S33.M01", contract_version, [manifest, inputs.get("quality_report_phase_2")]),
        "reason_codes": manifest.reason_codes,
        "quality_status": quality,
        "records": tuple(readiness_records),
        "ready_count": sum(item.status == ReadinessStatus.READY for item in readiness_records),
        "degraded_count": sum(item.status == ReadinessStatus.DEGRADED for item in readiness_records),
        "blocked_count": sum(item.status == ReadinessStatus.BLOCKED_UPSTREAM for item in readiness_records),
    })
    return manifest, report
