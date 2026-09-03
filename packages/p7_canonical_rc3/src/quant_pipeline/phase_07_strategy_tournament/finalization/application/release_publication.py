"""Validate final artifacts and build the P7 release receipt."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...canonical import build_canonical_artifact, digest
from ..artifacts import validate_artifact_integrity
from ..boundary.base import ArtifactEnvelope as FinalArtifactEnvelope
from ...learning.boundary import ArtifactEnvelope as LearningArtifactEnvelope
from ...foundation.models import ArtifactEnvelope as FoundationArtifactEnvelope
from ...foundation.artifacts import verify_artifact_hash as verify_foundation_artifact_hash
from ...errors import P7ContractError
from ...learning.domain.errors import P7LearningError
from ..errors import IntegrityViolation
from pydantic import ValidationError

REQUIRED_ARTIFACTS = (
    "ranked_strategy_candidate_panel", "ranking_audit_report",
    "ranked_strategy_execution_context_snapshot", "phase8_strategy_ranking_handoff_manifest",
)
SUBPHASE_BASELINES = {f"P7.S{subphase}": "2.3.1rc3" for subphase in range(1, 9)}


def _verify_canonical_artifact(artifact: Mapping[str, Any]) -> None:
    """Verify artifacts created by the top-level canonical builder."""
    name = str(artifact.get("artifact_name", ""))
    content_sha256 = str(artifact.get("content_sha256", ""))
    expected_id = f"{name}:{content_sha256[:24]}"
    if artifact.get("artifact_id") != expected_id:
        raise ValueError("canonical artifact_id mismatch")
    payload = {
        "artifact_name": name,
        "schema_version": artifact.get("schema_version"),
        "pipeline_version": artifact.get("pipeline_version"),
        "producer_phase": artifact.get("producer_phase"),
        "producer_module_id": artifact.get("producer_module_id"),
        "run_id": artifact.get("run_id"),
        "cycle_id": artifact.get("cycle_id"),
        "decision_time": artifact.get("decision_time"),
        "available_at": artifact.get("available_at"),
        "lineage_id": artifact.get("lineage_id"),
        "records": artifact.get("records", []),
    }
    if digest(payload) != content_sha256:
        raise ValueError("canonical artifact content hash mismatch")



def validate_required_artifacts(inputs: Mapping[str, Any]) -> None:
    missing = [name for name in REQUIRED_ARTIFACTS if name not in inputs]
    if missing:
        raise P7ContractError("P7_RELEASE_INPUT_MISSING", f"missing final artifacts: {missing}")


def single_record(artifact: Mapping[str, Any], artifact_name: str) -> Mapping[str, Any]:
    records = artifact.get("records")
    if artifact.get("record_count") != 1 or not isinstance(records, list) or len(records) != 1:
        raise P7ContractError("P7_RELEASE_ARTIFACT_INVALID", f"{artifact_name} must contain exactly one record")
    record = records[0]
    if not isinstance(record, Mapping):
        raise P7ContractError("P7_RELEASE_ARTIFACT_INVALID", f"{artifact_name} record must be an object")
    return record


def release_context(config: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, str]:
    context = config.get("context")
    if not isinstance(context, Mapping):
        raise P7ContractError("P7_RELEASE_CONTEXT_MISSING", "release context is required")
    values: dict[str, str] = {}
    for field in ("run_id", "cycle_id", "decision_time", "available_at", "created_at", "lineage_id"):
        value = context.get(field, audit.get(field))
        if value is None:
            raise P7ContractError("P7_RELEASE_CONTEXT_MISSING", f"release context is missing {field}")
        values[field] = str(value)
    return values


def artifact_references(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    references = []
    for name, artifact in sorted(inputs.items()):
        if not isinstance(artifact, Mapping) or "content_sha256" not in artifact:
            continue
        try:
            if int(artifact.get("record_count", -1)) != len(artifact.get("records", [])):
                raise ValueError("record_count mismatch")
            # S8.M04 independently authenticates the final boundary artifacts it certifies.
            # Upstream foundation/tournament artifacts were already authenticated at their ingress.
            if name in REQUIRED_ARTIFACTS:
                if "destination_phase" in artifact and "grain" in artifact:
                    foundation_envelope = FoundationArtifactEnvelope.model_validate(artifact)
                    if not verify_foundation_artifact_hash(foundation_envelope):
                        raise ValueError("foundation artifact hash mismatch")
                elif artifact.get("artifact_id") == f"{name}:{str(artifact.get('content_sha256', ''))[:20]}":
                    envelope = FinalArtifactEnvelope.model_validate(artifact)
                    validate_artifact_integrity(envelope, "P7.S8.M04")
                elif artifact.get("artifact_id") == f"{name}:{str(artifact.get('content_sha256', ''))[:24]}":
                    _verify_canonical_artifact(artifact)
                elif "pipeline_version" in artifact:
                    learning_envelope = LearningArtifactEnvelope.model_validate(artifact)
                    learning_envelope.verify()
                else:
                    envelope = FinalArtifactEnvelope.model_validate(artifact)
                    validate_artifact_integrity(envelope, "P7.S8.M04")
        except (ValueError, TypeError, KeyError, ValidationError, P7LearningError, IntegrityViolation) as exc:
            raise P7ContractError("P7_ARTIFACT_HASH_MISMATCH", f"invalid final artifact {name}: {exc}") from exc
        references.append({
        "artifact_name": name, "artifact_id": artifact.get("artifact_id"),
        "content_sha256": artifact.get("content_sha256"), "schema_version": artifact.get("schema_version"),
            "record_count": artifact.get("record_count"),
        })
    return references


def candidate_counts(audit: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, int]:
    upstream_blocked = inputs.get("eligibility_blocked_candidate_panel")
    upstream_count = int(upstream_blocked.get("record_count", 0)) if isinstance(upstream_blocked, Mapping) else 0
    final_received = int(audit.get("received_count", 0))
    final_blocked = int(audit.get("blocked_count", 0))
    return {
        "candidate_count_received": final_received + upstream_count,
        "candidate_count_ranked": int(audit.get("ranked_count", 0)),
        "candidate_count_blocked": final_blocked + upstream_count,
        "candidate_count_eligibility_blocked": upstream_count,
        "candidate_count_abstained": int(audit.get("abstained_count", 0)),
    }


def build_release_artifact(
    name: str, records: list[dict[str, Any]], context: Mapping[str, str], module_id: str
) -> dict[str, Any]:
    return build_canonical_artifact(
        name=name, records=records, module_id=module_id, run_id=context["run_id"],
        cycle_id=context["cycle_id"], decision_time=context["decision_time"],
        available_at=context["available_at"], created_at=context["created_at"],
        lineage_id=context["lineage_id"],
    )


def build_release_outputs(
    inputs: Mapping[str, Any], config: Mapping[str, Any], module_id: str
) -> dict[str, Any]:
    validate_required_artifacts(inputs)
    audit = single_record(inputs["ranking_audit_report"], "ranking_audit_report")
    if not audit.get("candidate_conservation_pass"):
        raise P7ContractError("P7_RELEASE_CONSERVATION_FAILED", "ranking audit did not prove candidate conservation")
    single_record(inputs["phase8_strategy_ranking_handoff_manifest"], "phase8_strategy_ranking_handoff_manifest")
    context = release_context(config, audit)
    references = artifact_references(inputs)
    closure_hash = digest(references)
    receipt_record = {
        "phase_id": "P7", "release_status": "PASS", "technical_closure": True,
        "economic_qualification": False, "production_promotion_allowed": False,
        **candidate_counts(audit, inputs), "reference_closure_sha256": closure_hash,
        "subphase_baselines": SUBPHASE_BASELINES, "release_version": "2.3.1rc3.post2",
    }
    manifest_record = {
        "phase_id": "P7", "contract_version": "2.3.0", "references": references,
        "reference_count": len(references), "reference_closure_sha256": closure_hash,
        "production_promotion_allowed": False,
    }
    return {
        "p7_phase_release_receipt": build_release_artifact(
            "p7_phase_release_receipt", [receipt_record], context, module_id
        ),
        "p7_phase_release_manifest": build_release_artifact(
            "p7_phase_release_manifest", [manifest_record], context, module_id
        ),
    }
