from __future__ import annotations

from typing import Any

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .errors import S9Error

LEGACY_PAYLOADS = (
    "underlying_feature_matrix_raw",
    "underlying_feature_matrix_selected",
    "underlying_feature_factors_pca",
    "underlying_feature_embeddings",
    "feature_selection_report",
    "feature_lineage_report",
    "drift_safety_report",
)


def _handoff_decision(gate: ArtifactEnvelope) -> str:
    decisions = [
        str(record["decision"])
        for record in gate.records
        if record["gate_scope"] == "HANDOFF"
    ]
    if len(decisions) != 1:
        raise S9Error("P4_S9_GATE_INVALID", "exactly one handoff gate decision is required")
    return decisions[0]


def _payload_record(name: str, artifact: ArtifactEnvelope) -> dict[str, Any]:
    return {
        "artifact_name": name,
        "artifact_id": artifact.artifact_id,
        "content_hash": artifact.content_hash,
        "schema_version": artifact.schema_version,
        "grain": list(artifact.grain),
        "record_count": artifact.record_count,
        "period_start": _period(artifact, "min"),
        "period_end": _period(artifact, "max"),
        "execution_status": artifact.execution_status,
        "quality_status": artifact.quality_status,
        "fit_state_ids": _fit_states(artifact),
        "limitations": _limitations(artifact),
    }


def _payload_records(available: dict[str, ArtifactEnvelope]) -> list[dict[str, Any]]:
    missing = [name for name in LEGACY_PAYLOADS if name not in available]
    if missing:
        raise S9Error("P4_S9_HANDOFF_INPUT_MISSING", f"missing legacy payloads: {missing}")
    return [_payload_record(name, available[name]) for name in LEGACY_PAYLOADS]


def _handoff_state(decision: str) -> tuple[bool, bool, bool]:
    blocked = decision == "BLOCK_HANDOFF"
    partial = decision == "PARTIAL_HANDOFF"
    degraded = decision in {"PASS_WITH_DEGRADATION", "PARTIAL_HANDOFF"}
    return blocked, partial, degraded


def _completeness(
    coverage: dict[str, Any], blocked: bool, partial: bool, degraded: bool
) -> str:
    fallback = (
        "BLOCKED" if blocked else "PARTIAL" if partial else "DEGRADED" if degraded else "COMPLETE"
    )
    return str(coverage.get("completeness_status", fallback))


def build_handoff(
    inputs: dict[str, ArtifactEnvelope],
    generated: dict[str, ArtifactEnvelope],
    context: ExecutionContext,
) -> ArtifactEnvelope:
    available = inputs | generated
    records = _payload_records(available)
    gate = generated["p4_quality_gate_decision"]
    decision = _handoff_decision(gate)
    supplemental = generated["model_consumer_view_manifest"]
    lineage = canonical_sha256(
        {
            "payloads": [(item["artifact_id"], item["content_hash"]) for item in records],
            "gate": gate.artifact_id,
            "views": supplemental.artifact_id,
        }
    )
    blocked, partial, degraded = _handoff_state(decision)
    coverage = gate.metadata.get("family_coverage", {})
    return build_artifact(
        artifact_name="phase5_feature_handoff_manifest",
        schema_version="v14.9-rc1",
        producer_module_id="P4.S9.M04",
        context=context,
        grain=("artifact_name",),
        records=records,
        lineage_id=lineage,
        metadata={
            "destination_phase": "phase_05_underlying_forecasts",
            "gate_decision": decision,
            "consumer_view_manifest_id": supplemental.artifact_id,
            "consumer_view_manifest_hash": supplemental.content_hash,
            "manifest_does_not_self_reference": True,
            "completeness_status": _completeness(coverage, blocked, partial, degraded),
            "family_coverage": coverage,
        },
        execution_status="BLOCKED" if blocked else ("DEGRADED" if degraded else "PRODUCED"),
        quality_status="BLOCKED" if blocked else ("DEGRADED" if degraded else "VALIDATED"),
    )

def _period(artifact: ArtifactEnvelope, mode: str) -> str | None:
    values = [
        str(record[key])
        for record in artifact.records
        for key in ("decision_time", "fit_end", "transform_end")
        if key in record
    ]
    if not values:
        return None
    return min(values) if mode == "min" else max(values)


def _fit_states(artifact: ArtifactEnvelope) -> list[str]:
    values: set[str] = set()
    for record in artifact.records:
        if record.get("fit_state_id"):
            values.add(str(record["fit_state_id"]))
        for item in record.get("feature_state_ids", {}).values():
            values.add(str(item))
    return sorted(values)


def _limitations(artifact: ArtifactEnvelope) -> list[str]:
    limitations: list[str] = []
    if artifact.execution_status.startswith("SKIPPED") or artifact.record_count == 0:
        limitations.append(f"{artifact.artifact_name} has no materialized records")
    if artifact.quality_status == "DEGRADED":
        limitations.append("artifact quality is degraded")
    return limitations
