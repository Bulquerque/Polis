from __future__ import annotations

from collections.abc import Iterable

from ..boundary.artifacts import ArtifactEnvelope
from ..boundary.records import HandoffManifestRecord
from .errors import ContractViolation, IntegrityViolation, TemporalViolation
from .reasoning import reason_prefix


def validate_common_identity(artifacts: Iterable[ArtifactEnvelope[object]], *, module_id: str) -> None:
    rows = tuple(artifacts)
    prefix = reason_prefix(module_id)
    if not rows:
        raise ContractViolation(f"{prefix}_EMPTY_ARTIFACT_SET", "at least one artifact is required", module_id=module_id)
    for field in ("run_id", "cycle_id", "decision_time"):
        values = {getattr(row, field) for row in rows}
        if len(values) != 1:
            raise ContractViolation(
                f"{prefix}_HANDOFF_IDENTITY_MISMATCH",
                f"input artifacts disagree on {field}",
                module_id=module_id,
                details={field: sorted(str(value) for value in values)},
            )
    if module_id.startswith("P7.S3"):
        decision_time = rows[0].decision_time
        future = [row.artifact_name for row in rows if row.available_at > decision_time]
        if future:
            raise TemporalViolation(
                f"{prefix}_ARTIFACT_AVAILABLE_AFTER_DECISION",
                "input artifact was not available at decision time",
                module_id=module_id,
                details={"artifacts": sorted(future)},
            )


def validate_policy_time(policy_artifact: ArtifactEnvelope[object], *, module_id: str) -> None:
    if policy_artifact.available_at > policy_artifact.decision_time:
        raise TemporalViolation(
            f"{reason_prefix(module_id)}_POLICY_AVAILABLE_AFTER_DECISION",
            "policy was not available at decision time",
            module_id=module_id,
            details={"artifact_id": policy_artifact.artifact_id},
        )


def validate_manifest_references(
    manifest: ArtifactEnvelope[HandoffManifestRecord],
    artifacts: dict[str, ArtifactEnvelope[object]],
    *,
    required_names: tuple[str, ...],
    module_id: str,
) -> None:
    prefix = reason_prefix(module_id)
    if len(manifest.records) != 1:
        raise ContractViolation(
            f"{prefix}_MANIFEST_RECORD_COUNT_INVALID",
            "handoff manifest must contain exactly one record",
            module_id=module_id,
        )
    refs = {ref.artifact_name: ref for ref in manifest.records[0].references}
    missing = sorted(set(required_names) - set(refs))
    if missing:
        raise ContractViolation(
            f"{prefix}_MANIFEST_REFERENCE_MISSING",
            "handoff manifest is missing required references",
            module_id=module_id,
            details={"missing": missing},
        )
    for name in required_names:
        artifact = artifacts[name]
        ref = refs[name]
        expected = (artifact.artifact_id, artifact.content_sha256, artifact.schema_version, artifact.record_count)
        received = (ref.artifact_id, ref.content_sha256, ref.schema_version, ref.record_count)
        if expected != received:
            raise IntegrityViolation(
                f"{prefix}_MANIFEST_REFERENCE_INVALID",
                f"manifest reference does not match {name}",
                module_id=module_id,
                details={"artifact": name},
            )
