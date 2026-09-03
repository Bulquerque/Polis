"""P7.S2.M04 — publish the immutable Foundation runtime foundation handoff."""

from __future__ import annotations

from pydantic import JsonValue, ValidationError

from ..artifacts import ArtifactEnvelope, create_artifact, verify_artifact_hash
from ..canonical import content_sha256
from ..models import ModuleConfig
from ..reason_codes import ReasonCode
from ..s2_errors import P7S2Error
from .models import FoundationHandoffRecord, HandoffArtifactReference

MODULE_ID = "P7.S2.M04"
EXPECTED = {
    "eligible_strategy_candidate_panel": "one_record_per_candidate",
    "eligibility_blocked_candidate_panel": "one_record_per_candidate",
    "eligibility_decision_panel": "one_record_per_candidate",
    "candidate_comparison_group_panel": "one_record_per_candidate",
    "candidate_metric_route_panel": "one_record_per_candidate_metric",
    "ranking_feedback_context": "one_record_per_promoted_feedback_item",
}


def execute(
    artifact_payloads: dict[str, dict[str, JsonValue]],
    config_payload: dict[str, JsonValue],
) -> dict[str, dict[str, JsonValue]]:
    before = content_sha256(artifact_payloads)
    config, artifacts = _parse_inputs(artifact_payloads, config_payload)
    _validate_cross_artifact_invariants(artifacts)
    references = tuple(_reference(artifacts[name]) for name in sorted(EXPECTED))
    identity = {
        "contract_version": "2.0.0",
        "semantic_version": "2.0.0",
        "producer_stage": "FOUNDATION",
        "artifacts": [item.model_dump(mode="json") for item in references],
    }
    handoff_record = FoundationHandoffRecord(
        handoff_id=f"foundation-{content_sha256(identity)}",
        contract_version="2.0.0",
        semantic_version="2.0.0",
        producer_stage="FOUNDATION",
        consumer_stages=("TOURNAMENT", "LEARNING"),
        artifacts=references,
    )
    manifest = create_artifact(
        artifact_name="runtime_foundation_handoff_manifest",
        records=[handoff_record.model_dump(mode="json")],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_phase_handoff",
    )
    after = content_sha256(artifact_payloads)
    if before != after:
        raise P7S2Error(
            ReasonCode.S2_INPUT_MUTATION_DETECTED,
            "handoff publication mutated its inputs",
            MODULE_ID,
        )
    return {"runtime_foundation_handoff_manifest": manifest.model_dump(mode="json")}


def _parse_inputs(payloads, config_payload):
    if set(payloads) != set(EXPECTED):
        raise P7S2Error(
            ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
            "Foundation handoff inputs do not match the frozen artifact set",
            MODULE_ID,
            {
                "missing": sorted(set(EXPECTED) - set(payloads)),
                "unexpected": sorted(set(payloads) - set(EXPECTED)),
            },
        )
    try:
        config = ModuleConfig.model_validate(config_payload)
        artifacts = {name: ArtifactEnvelope.model_validate(payloads[name]) for name in EXPECTED}
    except ValidationError as exc:
        raise P7S2Error(
            ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
            "Foundation handoff input failed schema validation",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    for name, expected_grain in EXPECTED.items():
        artifact = artifacts[name]
        if artifact.artifact_name != name:
            raise P7S2Error(
                ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
                "handoff artifact name conflicts with its input slot",
                MODULE_ID,
                {"slot": name, "artifact_name": artifact.artifact_name},
            )
        if not verify_artifact_hash(artifact):
            raise P7S2Error(
                ReasonCode.FOUNDATION_HANDOFF_HASH_MISMATCH,
                "handoff artifact hash does not reconcile",
                MODULE_ID,
                {"artifact_name": name},
            )
        if artifact.grain != expected_grain:
            raise P7S2Error(
                ReasonCode.FOUNDATION_HANDOFF_GRAIN_MISMATCH,
                "handoff artifact grain differs from the frozen contract",
                MODULE_ID,
                {"artifact_name": name, "grain": artifact.grain, "expected": expected_grain},
            )
        _validate_context(artifact, config)
    return config, artifacts


def _validate_context(artifact: ArtifactEnvelope, config: ModuleConfig) -> None:
    expected = config.context
    mismatches = {
        key: {"actual": getattr(artifact, key), "expected": getattr(expected, key)}
        for key in ("run_id", "cycle_id", "decision_time", "pipeline_version")
        if getattr(artifact, key) != getattr(expected, key)
    }
    if mismatches:
        raise P7S2Error(
            ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
            "handoff artifacts do not share the module context",
            MODULE_ID,
            {"artifact_name": artifact.artifact_name, "mismatches": mismatches},
        )


def _validate_cross_artifact_invariants(artifacts) -> None:
    eligible = _candidate_ids(artifacts["eligible_strategy_candidate_panel"])
    blocked = _candidate_ids(artifacts["eligibility_blocked_candidate_panel"])
    decisions = _candidate_ids(artifacts["eligibility_decision_panel"])
    groups = _candidate_ids(artifacts["candidate_comparison_group_panel"])
    routes = _candidate_ids(artifacts["candidate_metric_route_panel"])
    if eligible & blocked or decisions != eligible | blocked:
        raise P7S2Error(
            ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
            "eligibility partition does not conserve the candidate universe",
            MODULE_ID,
            {
                "eligible": sorted(eligible),
                "blocked": sorted(blocked),
                "decisions": sorted(decisions),
            },
        )
    if groups != eligible:
        raise P7S2Error(
            ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
            "comparison groups must cover exactly the eligible candidates",
            MODULE_ID,
            {"eligible": sorted(eligible), "groups": sorted(groups)},
        )
    if routes - eligible or (eligible and not routes):
        raise P7S2Error(
            ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
            "metric routes must reference only and all eligible candidates",
            MODULE_ID,
            {"eligible": sorted(eligible), "routes": sorted(routes)},
        )
    _validate_decision_statuses(artifacts["eligibility_decision_panel"], eligible, blocked)


def _candidate_ids(artifact: ArtifactEnvelope) -> set[str]:
    result: set[str] = set()
    for record in artifact.records:
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise P7S2Error(
                ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
                "candidate-grain handoff artifact contains an invalid candidate ID",
                MODULE_ID,
                {"artifact_name": artifact.artifact_name},
            )
        result.add(candidate_id)
    return result


def _validate_decision_statuses(artifact, eligible, blocked) -> None:
    seen: set[str] = set()
    for record in artifact.records:
        candidate_id = str(record["candidate_id"])
        status = record.get("status")
        if candidate_id in seen:
            raise P7S2Error(
                ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
                "eligibility decisions are not unique",
                MODULE_ID,
                {"candidate_id": candidate_id},
            )
        seen.add(candidate_id)
        expected = "ELIGIBLE" if candidate_id in eligible else "BLOCKED"
        if status != expected:
            raise P7S2Error(
                ReasonCode.FOUNDATION_HANDOFF_INCOMPLETE,
                "eligibility decision status conflicts with partition membership",
                MODULE_ID,
                {"candidate_id": candidate_id, "status": status, "expected": expected},
            )


def _reference(artifact: ArtifactEnvelope) -> HandoffArtifactReference:
    return HandoffArtifactReference(
        artifact_name=artifact.artifact_name,
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        schema_version=artifact.schema_version,
        record_count=artifact.record_count,
        grain=artifact.grain,
        producer_module_id=artifact.producer_module_id,
    )
