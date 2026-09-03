from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ...shared.assets import source_or_packaged_root
from .canonical import (
    content_hash,
    ensure_mapping,
    extract_records,
    format_utc,
    lineage_token,
    parse_aware_datetime,
    parse_cycle_id,
    require_fields,
    require_no_forbidden_fields,
    require_no_secrets,
    stable_sha256,
)
from .errors import Issue, S3ContractError
from .schemas import SchemaRegistry
from .validators import normalize_matured_feedback_item
from .ports import CommitmentResolverPort

REQUIRED_INPUTS = (
    "p9_belief_outcome_feedback_package",
    "phase3_learning_feedback_handoff_manifest",
    "phase3_run_snapshot",
)
_SCHEMA_PATH = "schemas/internal/active_belief_feedback_bundle.schema.yaml"


@dataclass(frozen=True, slots=True)
class _BeliefFeedbackInputs:
    snapshot: dict[str, Any]
    package: dict[str, Any]
    manifest: dict[str, Any]
    as_of: datetime
    current_cycle: int
    processed_at: str
    registry: SchemaRegistry


def _schema_registry(config: dict[str, Any]) -> SchemaRegistry:
    package_root = config.get("package_root")
    root = Path(package_root) if package_root else source_or_packaged_root()
    return SchemaRegistry(root)


def _validated_inputs(
    inputs: dict[str, Any],
    execution: dict[str, Any],
) -> _BeliefFeedbackInputs:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise S3ContractError("P3_S3_M02_INPUT_INVALID", f"missing required inputs: {missing}")
    values = {name: deepcopy(ensure_mapping(inputs[name], name)) for name in REQUIRED_INPUTS}
    for name, value in values.items():
        require_no_forbidden_fields(value, name)
        require_no_secrets(value, name)

    snapshot = values["phase3_run_snapshot"]
    package = values["p9_belief_outcome_feedback_package"]
    manifest = values["phase3_learning_feedback_handoff_manifest"]
    require_fields(snapshot, ["identity", "temporal", "lineage_id"], location="phase3_run_snapshot")
    require_fields(
        package,
        [
            "schema_version",
            "contract_version",
            "artifact_id",
            "created_at",
            "lineage_id",
            "status",
            "feedback_items",
        ],
        location="p9_belief_outcome_feedback_package",
    )
    require_fields(
        manifest,
        [
            "schema_version",
            "contract_version",
            "artifact_id",
            "created_at",
            "lineage_id",
            "status",
            "feedback_artifact_id",
        ],
        location="phase3_learning_feedback_handoff_manifest",
    )
    as_of = parse_aware_datetime(snapshot["temporal"]["as_of"], field="phase3_run_snapshot.temporal.as_of")
    current_cycle = parse_cycle_id(execution.get("current_cycle_id"), field="current_cycle_id")
    processed_at = format_utc(parse_aware_datetime(execution.get("processed_at"), field="processed_at"))
    registry = _schema_registry(execution)
    registry.validate(
        "schemas/extensions/p9_belief_outcome_feedback_package.schema.yaml",
        package,
        label="p9_belief_outcome_feedback_package",
    )
    registry.validate(
        "schemas/extensions/phase3_learning_feedback_handoff_manifest.schema.yaml",
        manifest,
        label="phase3_learning_feedback_handoff_manifest",
    )
    if _created_at(package, "package") > as_of or _created_at(manifest, "manifest") > as_of:
        raise S3ContractError(
            "P3_S3_M02_FUTURE_HANDOFF",
            "feedback handoff created after as_of",
        )
    if lineage_token(package) != lineage_token(manifest):
        raise S3ContractError("P3_S3_M02_LINEAGE_MISMATCH", "P9 package and manifest lineage differ")
    if manifest["feedback_artifact_id"] != package["artifact_id"]:
        raise S3ContractError(
            "P3_S3_M02_MANIFEST_REFERENCE_MISMATCH",
            "manifest does not reference package",
        )
    return _BeliefFeedbackInputs(
        snapshot=snapshot,
        package=package,
        manifest=manifest,
        as_of=as_of,
        current_cycle=current_cycle,
        processed_at=processed_at,
        registry=registry,
    )


def _created_at(value: dict[str, Any], label: str) -> datetime:
    return parse_aware_datetime(value["created_at"], field=f"{label}.created_at")


def _base_output(prepared: _BeliefFeedbackInputs) -> dict[str, Any]:
    return {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p3.s3.active_belief_feedback_bundle.v2",
        "run_id": prepared.snapshot["identity"]["run_id"],
        "snapshot_id": prepared.snapshot["identity"]["snapshot_id"],
        "current_cycle_id": prepared.current_cycle,
        "source_package": {
            "artifact_id": prepared.package["artifact_id"],
            "lineage_id": prepared.package["lineage_id"],
        },
        "source_manifest": {
            "artifact_id": prepared.manifest["artifact_id"],
            "lineage_id": prepared.manifest["lineage_id"],
        },
        "created_at": prepared.processed_at,
    }


def _no_feedback_output(prepared: _BeliefFeedbackInputs) -> dict[str, Any]:
    if prepared.package["feedback_items"]:
        raise S3ContractError(
            "P3_S3_M02_EMPTY_STATUS_HAS_ITEMS",
            "NO_MATURED_FEEDBACK cannot contain items",
        )
    seed = [prepared.package["artifact_id"], prepared.snapshot["identity"]["snapshot_id"]]
    return {
        **_base_output(prepared),
        "status": "NO_MATURED_FEEDBACK",
        "feedback_items": [],
        "issues": [
            Issue(
                "P3_S3_M02_NO_MATURED_FEEDBACK",
                "INFO",
                "No matured belief feedback is available for this cycle",
                "p9_belief_outcome_feedback_package",
            ).as_dict()
        ],
        "lineage_id": f"lineage-active-belief-{stable_sha256(seed)[:16]}",
    }


def _normalized_feedback(prepared: _BeliefFeedbackInputs, execution: dict[str, Any]) -> list[dict[str, Any]]:
    records = extract_records(prepared.package, "p9_belief_outcome_feedback_package")
    if not records:
        raise S3ContractError(
            "P3_S3_M02_ACTIVE_STATUS_EMPTY",
            "ACTIVE feedback package must contain at least one item",
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_commitments: set[str] = set()
    resolver = execution.get("commitment_resolver")
    qualification = str(execution.get("execution_profile", "DEVELOPMENT")).upper() == "QUALIFICATION"
    if qualification and (resolver is None or not callable(getattr(resolver, "resolve", None))):
        raise S3ContractError("P3_S3_M02_COMMITMENT_RESOLVER_REQUIRED", "qualification requires commitment resolver")
    for item in records:
        value = normalize_matured_feedback_item(
            item,
            current_cycle=prepared.current_cycle,
            as_of=prepared.as_of,
        )
        feedback_id = value["feedback_id"]
        if feedback_id in seen:
            raise S3ContractError("P3_S3_M02_DUPLICATE_FEEDBACK_ID", feedback_id)
        seen.add(feedback_id)
        commitment_id=value["commitment_id"]
        if commitment_id in seen_commitments:
            raise S3ContractError("P3_S3_M02_DUPLICATE_COMMITMENT_FEEDBACK", commitment_id)
        seen_commitments.add(commitment_id)
        if resolver is not None:
            commitment=ensure_mapping(resolver.resolve(commitment_id),f"commitment:{commitment_id}")
            for field in ("commitment_id","commit_hash","person_id","proposition_id","horizon"):
                expected=value[field]; observed=commitment.get(field)
                if str(observed)!=str(expected): raise S3ContractError("P3_S3_M02_COMMITMENT_MATCH_FAILED",f"{commitment_id}:{field}")
            value["commitment_match_status"]="VERIFIED"
            value["commitment_source_hash"]=stable_sha256(commitment)
        else:
            value["commitment_match_status"]="PACKAGE_ASSERTED"
            value["commitment_source_hash"]=None
        normalized.append(value)
    normalized.sort(key=lambda item: (item["person_id"], item["proposition_id"], item["horizon"], item["feedback_id"]))
    return normalized


def _active_feedback_output(
    prepared: _BeliefFeedbackInputs,
    feedback_items: list[dict[str, Any]],
) -> dict[str, Any]:
    seed = [item["feedback_id"] for item in feedback_items]
    seed.append(prepared.snapshot["identity"]["snapshot_id"])
    return {
        **_base_output(prepared),
        "status": "ACTIVE",
        "feedback_items": feedback_items,
        "issues": [],
        "lineage_id": f"lineage-active-belief-{stable_sha256(seed)[:16]}",
    }


def _finalize(prepared: _BeliefFeedbackInputs, output: dict[str, Any]) -> dict[str, Any]:
    output["content_hash"] = content_hash(output)
    prepared.registry.validate(_SCHEMA_PATH, output, label="active_belief_feedback_bundle")
    return output


def ingest_matured_belief_feedback(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Activate only matured, prior-cycle belief outcome feedback."""

    prepared = _validated_inputs(inputs, dict(config or {}))
    if prepared.package["status"] == "NO_MATURED_FEEDBACK":
        return _finalize(prepared, _no_feedback_output(prepared))
    return _finalize(prepared, _active_feedback_output(prepared, _normalized_feedback(prepared, dict(config or {}))))
