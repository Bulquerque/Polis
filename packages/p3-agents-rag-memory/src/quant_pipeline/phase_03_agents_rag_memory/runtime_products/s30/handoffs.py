from __future__ import annotations

from time import perf_counter
from typing import Any, Mapping

from ...s30_models import (
    AgentDisagreementPanel, ArtifactManifestEntry, BeliefOutcomeCommitmentLog,
    ConsumerBindingStatus, ContextMemoryFeaturePanel, EvidenceTagPanel,
    ExecutionContext, HypothesisRegistry, Phase3RunSnapshot,
    Phase4SocialHandoffManifest, SocialFeaturePanel, ValidatedSocietyStatePanel,
    VariableEvolutionInputManifest,
)
from .common import (
    S30ContractError, S30IntegrityError, _artifact_id, _digest, _lineage_id,
    _module_result, _parse, _quality_rollup, _scan_forbidden,
    _validate_artifact_alignment,
)

ARTIFACT_GRAINS: dict[str, tuple[str, ...]] = {
    "social_feature_panel": ("date", "underlying", "social_feature_id"),
    "evidence_tag_panel": ("underlying", "proposition_id", "horizon", "claim_id", "evidence_id"),
    "agent_disagreement_panel": ("underlying", "proposition_id", "horizon", "as_of_date"),
    "context_memory_feature_panel": (
        "underlying",
        "proposition_id",
        "horizon",
        "context_memory_feature_id",
    ),
    "hypothesis_registry": ("hypothesis_id", "created_at"),
}
PRODUCER_MODULES = {
    "social_feature_panel": "P3.S30.M01",
    "evidence_tag_panel": "P3.S29.M02",
    "agent_disagreement_panel": "P3.S29.M01",
    "context_memory_feature_panel": "P3.S30.M02",
    "hypothesis_registry": "P3.S30.M03",
}


def _manifest_entry(name: str, artifact: Any) -> ArtifactManifestEntry:
    payload = artifact.model_dump(mode="json")
    return ArtifactManifestEntry(
        artifact_name=name,  # type: ignore[arg-type]
        artifact_id=artifact.artifact_id,
        schema_id=artifact.schema_id,
        schema_version=artifact.schema_version,
        content_hash=_digest(payload),
        row_count=len(artifact.records),
        grain=ARTIFACT_GRAINS[name],
        producer_module_id=PRODUCER_MODULES[name],
        lineage_id=artifact.lineage_id,
        available_at=artifact.created_at,
        quality_status=artifact.quality_status,
    )


def build_phase4_social_handoff(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
    expected_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate the five payload outputs and freeze the sixth official output: the manifest."""

    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    required = {
        "social_feature_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
        "context_memory_feature_panel",
        "hypothesis_registry",
        "phase3_run_snapshot",
    }
    missing = sorted(required - set(inputs))
    if missing:
        raise S30ContractError(f"P3.S30.M04 missing required inputs: {missing}")

    context = _parse(ExecutionContext, context_value, "execution_context")
    social = _parse(SocialFeaturePanel, inputs["social_feature_panel"], "social_feature_panel")
    evidence = _parse(EvidenceTagPanel, inputs["evidence_tag_panel"], "evidence_tag_panel")
    disagreement = _parse(
        AgentDisagreementPanel,
        inputs["agent_disagreement_panel"],
        "agent_disagreement_panel",
    )
    memory = _parse(
        ContextMemoryFeaturePanel,
        inputs["context_memory_feature_panel"],
        "context_memory_feature_panel",
    )
    hypotheses = _parse(HypothesisRegistry, inputs["hypothesis_registry"], "hypothesis_registry")
    snapshot = _parse(Phase3RunSnapshot, inputs["phase3_run_snapshot"], "phase3_run_snapshot")
    _validate_artifact_alignment(context, (social, evidence, disagreement, memory, hypotheses))
    if (
        snapshot.run_id != context.run_id
        or snapshot.cycle_id != context.cycle_id
        or snapshot.as_of_time != context.as_of_time
        or snapshot.pipeline_version != context.pipeline_version
    ):
        raise S30ContractError("phase3_run_snapshot does not match execution context")

    artifacts = {
        "social_feature_panel": social,
        "evidence_tag_panel": evidence,
        "agent_disagreement_panel": disagreement,
        "context_memory_feature_panel": memory,
        "hypothesis_registry": hypotheses,
    }
    entries = tuple(_manifest_entry(name, artifact) for name, artifact in artifacts.items())
    if expected_hashes is not None:
        unknown = set(expected_hashes) - set(artifacts)
        if unknown:
            raise S30IntegrityError(f"expected hashes contain unknown artifacts: {sorted(unknown)}")
        actual = {entry.artifact_name: entry.content_hash for entry in entries}
        mismatches = {
            name: {"expected": value, "actual": actual[name]}
            for name, value in expected_hashes.items()
            if actual[name] != value
        }
        if mismatches:
            raise S30IntegrityError(f"artifact hash mismatch: {mismatches}")

    statuses = [entry.quality_status for entry in entries]
    payload = [entry.model_dump(mode="json") for entry in entries]
    output = Phase4SocialHandoffManifest(
        artifact_id=_artifact_id("phase4-social-handoff-manifest", payload),
        created_at=context.created_at,
        lineage_id=_lineage_id(
            "phase4-social-handoff-manifest",
            {
                "snapshot": snapshot.lineage_id,
                "entries": payload,
            },
        ),
        pipeline_version=context.pipeline_version,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        schema_id="p3.s30.phase4_social_handoff_manifest.semantic",
        schema_version="1.0.0",
        quality_status=_quality_rollup(statuses),
        quality_reasons=tuple(
            sorted(
                {
                    reason
                    for artifact in artifacts.values()
                    for reason in artifact.quality_reasons
                }
            )
        ),
        entries=entries,
    )
    _scan_forbidden(output)
    return _module_result(
        "P3.S30.M04",
        "phase4_social_handoff_builder",
        "phase4_social_handoff_manifest",
        output,
        started_at,
    )


def build_variable_evolution_handoff(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a reference-only future P4 Variable Evolution input manifest."""

    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    required = {
        "validated_society_state_panel",
        "social_feature_panel",
        "context_memory_feature_panel",
        "hypothesis_registry",
        "belief_outcome_commitment_log",
        "phase3_run_snapshot",
    }
    missing = sorted(required - set(inputs))
    if missing:
        raise S30ContractError(f"P3.S30.M05 missing required inputs: {missing}")

    context = _parse(ExecutionContext, context_value, "execution_context")
    society = _parse(
        ValidatedSocietyStatePanel,
        inputs["validated_society_state_panel"],
        "validated_society_state_panel",
    )
    social = _parse(SocialFeaturePanel, inputs["social_feature_panel"], "social_feature_panel")
    memory = _parse(
        ContextMemoryFeaturePanel,
        inputs["context_memory_feature_panel"],
        "context_memory_feature_panel",
    )
    hypotheses = _parse(HypothesisRegistry, inputs["hypothesis_registry"], "hypothesis_registry")
    commitments = _parse(
        BeliefOutcomeCommitmentLog,
        inputs["belief_outcome_commitment_log"],
        "belief_outcome_commitment_log",
    )
    snapshot = _parse(Phase3RunSnapshot, inputs["phase3_run_snapshot"], "phase3_run_snapshot")
    _validate_artifact_alignment(context, (society, social, memory, hypotheses, commitments))
    if (
        snapshot.run_id != context.run_id
        or snapshot.cycle_id != context.cycle_id
        or snapshot.as_of_time != context.as_of_time
        or snapshot.pipeline_version != context.pipeline_version
    ):
        raise S30ContractError("phase3_run_snapshot does not match execution context")

    reference_payload = {
        "society": society.artifact_id,
        "social": social.artifact_id,
        "memory": memory.artifact_id,
        "hypotheses": hypotheses.artifact_id,
        "commitments": commitments.artifact_id,
        "snapshot": snapshot.snapshot_id,
        "consumer_binding": ConsumerBindingStatus.CONSUMER_NOT_YET_BOUND,
    }
    output = VariableEvolutionInputManifest(
        manifest_id=_artifact_id("variable-evolution-input-manifest", reference_payload),
        canonical_society_state_ref=society.artifact_id,
        social_feature_ref=social.artifact_id,
        context_memory_feature_ref=memory.artifact_id,
        hypothesis_registry_ref=hypotheses.artifact_id,
        belief_commitment_ref=commitments.artifact_id,
        as_of_time=context.as_of_time.isoformat().replace("+00:00", "Z"),
        lineage_id=_lineage_id("variable-evolution-input-manifest", reference_payload),
    )
    _scan_forbidden(output)
    return _module_result(
        "P3.S30.M05",
        "variable_evolution_handoff_builder",
        "variable_evolution_input_manifest",
        output,
        started_at,
    )
