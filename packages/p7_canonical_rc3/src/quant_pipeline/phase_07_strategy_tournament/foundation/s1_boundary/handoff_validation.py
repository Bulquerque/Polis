"""P7.S1.M01 — validate the complete P6 handoff and artifact envelopes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from ..artifacts import create_artifact, verify_artifact_hash
from ..errors import P7S1Error
from ..models import ArtifactEnvelope, ManifestArtifactRef, ModuleConfig, P6HandoffManifest, major
from ..reason_codes import ReasonCode

MODULE_ID = "P7.S1.M01"

REQUIRED_ARTIFACTS = (
    "strategy_candidate_panel",
    "strategy_leg_panel",
    "strategy_market_snapshot",
    "strategy_payoff_panel",
    "strategy_scenario_evaluation_panel",
    "strategy_risk_panel",
    "strategy_cost_liquidity_panel",
    "strategy_lineage_panel",
    "strategy_generation_trace_panel",
    "candidate_rejection_report",
    "candidate_generation_audit",
)
OPTIONAL_ARTIFACTS = (
    "strategy_ambiguity_evaluation_panel",
    "strategy_greek_panel",
    "candidate_equivalence_panel",
    "quality_diversity_archive",
    "candidate_feature_base_panel",
)


class HandoffPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    required_artifacts: tuple[str, ...] = REQUIRED_ARTIFACTS
    optional_artifacts: tuple[str, ...] = OPTIONAL_ARTIFACTS
    accepted_contract_major: int = Field(default=2, ge=1)
    accepted_schema_major: int = Field(default=2, ge=1)


def execute(
    manifest_payload: dict[str, JsonValue],
    artifact_payloads: list[dict[str, JsonValue]],
    config_payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    config, policy, manifest, artifacts = _parse_inputs(
        manifest_payload,
        artifact_payloads,
        config_payload,
    )
    _validate_manifest_identity(manifest, config, policy)
    refs, supplied = _map_artifacts(manifest, artifacts)
    _validate_contract_surface(refs, supplied, policy)
    verified = _verify_all(supplied, refs, manifest, policy)
    return _build_outputs(config, policy, manifest, artifacts, verified)


def _parse_inputs(manifest_payload, artifact_payloads, config_payload):
    try:
        config = ModuleConfig.model_validate(config_payload)
        policy = HandoffPolicy.model_validate(config.policy)
        manifest = P6HandoffManifest.model_validate(manifest_payload)
        artifacts = tuple(ArtifactEnvelope.model_validate(item) for item in artifact_payloads)
    except ValidationError as exc:
        raise P7S1Error(
            ReasonCode.P6_MANIFEST_INVALID,
            "P6 handoff or module configuration failed validation",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    return config, policy, manifest, artifacts


def _map_artifacts(manifest, artifacts):
    refs = {item.artifact_name: item for item in manifest.artifacts}
    supplied = {item.artifact_name: item for item in artifacts}
    if len(supplied) != len(artifacts):
        raise P7S1Error(
            ReasonCode.P6_MANIFEST_INVALID,
            "supplied P6 artifact names must be unique",
            MODULE_ID,
        )
    return refs, supplied


def _validate_contract_surface(refs, supplied, policy) -> None:
    allowed = set(policy.required_artifacts) | set(policy.optional_artifacts)
    undeclared = sorted(set(supplied) - set(refs))
    unknown = sorted(set(refs) - allowed)
    missing_declared = sorted(set(refs) - set(supplied))
    missing_required = sorted(set(policy.required_artifacts) - set(refs))
    if undeclared or unknown:
        raise P7S1Error(
            ReasonCode.P6_ARTIFACT_UNDECLARED,
            "P6 supplied or declared an artifact outside the frozen contract",
            MODULE_ID,
            {"supplied_undeclared": undeclared, "manifest_unknown": unknown},
        )
    required_flag_errors = sorted(
        name for name in policy.required_artifacts if name in refs and not refs[name].required
    )
    if missing_declared or missing_required or required_flag_errors:
        raise P7S1Error(
            ReasonCode.P6_MANIFEST_INVALID,
            "P6 handoff is missing declared or required artifacts",
            MODULE_ID,
            {
                "missing_declared": missing_declared,
                "missing_required": missing_required,
                "required_flag_errors": required_flag_errors,
            },
        )


def _verify_all(supplied, refs, manifest, policy):
    verified: list[dict[str, JsonValue]] = []
    for name in sorted(supplied):
        envelope = supplied[name]
        _validate_artifact(envelope, refs[name], manifest, policy)
        verified.append(envelope.model_dump(mode="json"))
    return verified


def _build_outputs(config, policy, manifest, artifacts, verified):
    index_record = {
        "manifest": manifest.model_dump(mode="json"),
        "artifacts": verified,
        "artifact_names": sorted(item.artifact_name for item in artifacts),
    }
    report_record = {
        "status": "PASS",
        "manifest_id": manifest.manifest_id,
        "required_count": len(policy.required_artifacts),
        "optional_present_count": len({item.artifact_name for item in artifacts} & set(policy.optional_artifacts)),
        "verified_artifact_count": len(verified),
        "verified_record_count": sum(item.record_count for item in artifacts),
    }
    index = create_artifact(
        artifact_name="verified_p6_artifact_index",
        records=[index_record],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_handoff",
    )
    report = create_artifact(
        artifact_name="p6_handoff_validation_report",
        records=[report_record],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_handoff",
    )
    return {
        "verified_p6_artifact_index": index.model_dump(mode="json"),
        "p6_handoff_validation_report": report.model_dump(mode="json"),
    }


def _validate_manifest_identity(manifest, config, policy) -> None:
    if (
        major(manifest.contract_version) != policy.accepted_contract_major
        or major(manifest.schema_version) != policy.accepted_schema_major
    ):
        raise P7S1Error(
            ReasonCode.P6_SCHEMA_INCOMPATIBLE,
            "P6 contract major version is not accepted",
            MODULE_ID,
            {"contract_version": manifest.contract_version},
        )
    expected = config.context
    mismatches = _identity_mismatches(manifest, expected)
    if mismatches:
        raise P7S1Error(
            ReasonCode.P6_CLOCK_MISMATCH,
            "P6 manifest identity or clock does not match the P7 run context",
            MODULE_ID,
            {"mismatches": mismatches},
        )


def _identity_mismatches(manifest, expected):
    pairs = (
        ("run_id", manifest.run_id, expected.run_id),
        ("cycle_id", manifest.cycle_id, expected.cycle_id),
        ("decision_time", manifest.decision_time.isoformat(), expected.decision_time.isoformat()),
        ("pipeline_version", manifest.pipeline_version, expected.pipeline_version),
    )
    return {key: [actual, wanted] for key, actual, wanted in pairs if actual != wanted}


def _validate_artifact(
    envelope: ArtifactEnvelope,
    ref: ManifestArtifactRef,
    manifest: P6HandoffManifest,
    policy: HandoffPolicy,
) -> None:
    if major(envelope.schema_version) != policy.accepted_schema_major:
        raise P7S1Error(
            ReasonCode.P6_SCHEMA_INCOMPATIBLE,
            "P6 artifact schema major version is not accepted",
            MODULE_ID,
            {"artifact_name": envelope.artifact_name, "schema_version": envelope.schema_version},
        )
    _validate_reference_identity(envelope, ref)
    if not verify_artifact_hash(envelope):
        raise P7S1Error(
            ReasonCode.P6_HASH_MISMATCH,
            "P6 artifact content hash does not match its content",
            MODULE_ID,
            {"artifact_name": envelope.artifact_name},
        )
    if not _artifact_clock_is_valid(envelope, manifest):
        raise P7S1Error(
            ReasonCode.P6_CLOCK_MISMATCH,
            "P6 artifact producer, destination or clock is invalid",
            MODULE_ID,
            {"artifact_name": envelope.artifact_name},
        )


def _validate_reference_identity(envelope, ref) -> None:
    pairs = (
        (envelope.artifact_id, ref.artifact_id),
        (envelope.content_sha256, ref.content_sha256),
        (envelope.schema_version, ref.schema_version),
        (envelope.record_count, ref.record_count),
        (envelope.grain, ref.grain),
    )
    if any(left != right for left, right in pairs):
        raise P7S1Error(
            ReasonCode.P6_MANIFEST_INVALID,
            "P6 artifact envelope does not reconcile with its manifest reference",
            MODULE_ID,
            {"artifact_name": envelope.artifact_name},
        )


def _artifact_clock_is_valid(envelope, manifest) -> bool:
    return all(
        (
            envelope.producer_phase == "P6",
            envelope.destination_phase == "P7",
            envelope.run_id == manifest.run_id,
            envelope.cycle_id == manifest.cycle_id,
            envelope.decision_time == manifest.decision_time,
            envelope.available_at <= manifest.decision_time,
        )
    )
