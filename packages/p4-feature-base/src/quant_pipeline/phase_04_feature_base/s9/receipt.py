from __future__ import annotations

from typing import Any

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact


def _receipt_record(manifest: ArtifactEnvelope, receipt: ArtifactEnvelope) -> tuple[dict[str, Any], bool]:
    record = receipt.records[0]
    expected_ids = {str(item["artifact_id"]) for item in manifest.records}
    accepted = set(map(str, record.get("accepted_artifact_ids", [])))
    rejected = set(map(str, record.get("rejected_artifact_ids", [])))
    adaptations = list(record.get("adaptations_applied", []))
    issues: list[str] = []
    checks = (
        (record.get("handoff_manifest_id") == manifest.artifact_id, "manifest_id_mismatch"),
        (record.get("handoff_manifest_hash") == manifest.content_hash, "manifest_hash_mismatch"),
        (record.get("consumer_phase") == "phase_05_underlying_forecasts", "consumer_phase_invalid"),
        (not (expected_ids - accepted), "not_all_payloads_accepted"),
        (not rejected, "payloads_rejected"),
        (not adaptations, "silent_adaptations_not_allowed"),
    )
    issues.extend(issue for passed, issue in checks if not passed)
    valid = not issues
    return {
        "receipt_status": "VALIDATED" if valid else "REJECTED", "manifest_id": manifest.artifact_id,
        "manifest_hash": manifest.content_hash, "consumer_phase": record.get("consumer_phase"),
        "accepted_artifact_ids": sorted(accepted), "rejected_artifact_ids": sorted(rejected),
        "adaptations_applied": adaptations, "issues": issues,
    }, valid


def _build_receipt_artifact(
    manifest: ArtifactEnvelope, context: ExecutionContext, lineage: str,
    record: dict[str, Any], valid: bool,
) -> ArtifactEnvelope:
    return build_artifact(
        artifact_name="p4_to_p5_integration_receipt", schema_version="v14.9-rc1",
        producer_module_id="P4.S9.M05", context=context, grain=("receipt_status",),
        records=[record], lineage_id=lineage,
        execution_status="PRODUCED" if valid else "BLOCKED",
        quality_status="VALIDATED" if valid else "BLOCKED",
    )


def validate_receipt(
    manifest: ArtifactEnvelope, receipt: ArtifactEnvelope | None, context: ExecutionContext,
) -> ArtifactEnvelope:
    lineage = canonical_sha256({"manifest": manifest.artifact_id, "receipt": None if receipt is None else receipt.artifact_id})
    if receipt is None:
        record = {
            "receipt_status": "SKIPPED_NOT_AVAILABLE", "manifest_id": manifest.artifact_id,
            "manifest_hash": manifest.content_hash, "consumer_phase": "phase_05_underlying_forecasts",
            "accepted_artifact_ids": [], "rejected_artifact_ids": [], "adaptations_applied": [],
            "issues": ["phase5_consumption_receipt_not_provided"],
        }
        return build_artifact(
            artifact_name="p4_to_p5_integration_receipt", schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M05", context=context, grain=("receipt_status",),
            records=[record], lineage_id=lineage, execution_status="SKIPPED_NOT_AVAILABLE",
            quality_status="NOT_EVALUATED",
        )
    if receipt.record_count != 1:
        record = {
            "receipt_status": "REJECTED", "manifest_id": manifest.artifact_id,
            "manifest_hash": manifest.content_hash, "consumer_phase": None,
            "accepted_artifact_ids": [], "rejected_artifact_ids": [], "adaptations_applied": [],
            "issues": ["receipt must contain exactly one record"],
        }
        return _build_receipt_artifact(manifest, context, lineage, record, False)
    record, valid = _receipt_record(manifest, receipt)
    return _build_receipt_artifact(manifest, context, lineage, record, valid)
