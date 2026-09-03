from __future__ import annotations

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S31_M02_p9_context_learning_handoff_builder import (
    run_module as run_m02_wrapper,
)
from quant_pipeline.phase_03_agents_rag_memory.s31_models import (
    CommitmentMaturityEntry,
    ConsumerBindingStatus,
    EvaluationReadiness,
    ModelKnowledgeCutoffReport,
    P9ConsumerCompatibilityConfig,
    P9ContextLearningHandoffManifest,
    P9EvaluationEvidenceBundle,
)
from quant_pipeline.phase_03_agents_rag_memory.s31_products import (
    S31ContractError,
    S31IntegrityError,
    S31TemporalError,
)
from .s31_support import compatibility_config, execution_context, m01_inputs, run_m01, run_m02


def test_m02_wrapper_requires_execution_context():
    with pytest.raises(ValueError, match="execution context"):
        run_m02_wrapper({}, {"p9_consumer_compatibility": compatibility_config()})


def test_models_reject_naive_datetime_and_invalid_windows():
    context = execution_context()
    context["created_at"] = "2024-01-31T20:00:00"
    with pytest.raises(S31ContractError, match="timezone-aware"):
        run_m01(context=context)

    inputs = m01_inputs()
    inputs["model_knowledge_cutoff_report"]["evaluation_start"] = "2024-01-31T18:00:00Z"
    inputs["model_knowledge_cutoff_report"]["evaluation_end"] = "2024-01-31T17:00:00Z"
    with pytest.raises(S31ContractError, match="evaluation_end must not be before"):
        run_m01(inputs)


def test_commitment_model_rejects_non_forward_maturity():
    with pytest.raises(ValidationError, match="matures_at must be after"):
        CommitmentMaturityEntry.model_validate(
            {
                "commitment_id": "c-1",
                "commitment_hash": "a" * 64,
                "person_id": "person-1",
                "underlying_id": "u-1",
                "proposition_id": "prop-1",
                "horizon": "1M",
                "belief_value": 0.2,
                "confidence": 0.6,
                "evidence_refs": [],
                "committed_at": "2024-01-31T18:00:00Z",
                "matures_at": "2024-01-31T18:00:00Z",
                "readiness": EvaluationReadiness.PENDING_MATURITY,
                "lineage_id": "lin-1",
            },
            strict=False,
        )


def test_bundle_model_rejects_duplicate_artifact_set():
    bundle = run_m01()
    bundle["items"][1] = deepcopy(bundle["items"][0])
    with pytest.raises(ValidationError, match="exactly the six"):
        P9EvaluationEvidenceBundle.model_validate_json(json.dumps(bundle), strict=True)


def test_consumer_config_rejects_bound_inputs_with_unbound_status():
    config = compatibility_config()
    config["declared_p9_inputs"] = (
        "p9_evaluation_evidence_bundle",
        "p9_context_learning_handoff_manifest",
    )
    config["consumer_binding_status"] = ConsumerBindingStatus.CONSUMER_NOT_YET_BOUND
    with pytest.raises(ValidationError, match="status says not bound"):
        P9ConsumerCompatibilityConfig.model_validate(config, strict=True)


def test_handoff_model_rejects_wrong_hash_set_and_bad_digest():
    manifest = run_m02()
    missing = deepcopy(manifest)
    del missing["artifact_hashes"]["phase3_run_snapshot"]
    with pytest.raises(ValidationError, match="exactly the four"):
        P9ContextLearningHandoffManifest.model_validate_json(json.dumps(missing), strict=True)

    malformed = deepcopy(manifest)
    malformed["artifact_hashes"]["phase3_run_snapshot"] = "not-a-digest"
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        P9ContextLearningHandoffManifest.model_validate_json(json.dumps(malformed), strict=True)


def test_m01_rejects_alignment_and_reference_mismatches():
    cases = []
    a = m01_inputs()
    a["phase4_social_handoff_manifest"]["created_at"] = "2024-02-01T00:00:00Z"
    cases.append((a, S31TemporalError, "created_at is after"))

    b = m01_inputs()
    b["phase3_run_snapshot"]["as_of_time"] = "2024-01-31T19:00:00Z"
    cases.append((b, S31TemporalError, "Phase3RunSnapshot.as_of_time"))

    c = m01_inputs()
    c["variable_evolution_input_manifest"]["as_of_time"] = "2024-01-31T19:00:00Z"
    cases.append((c, S31TemporalError, "VariableEvolutionInputManifest.as_of_time"))

    d = m01_inputs()
    d["variable_evolution_input_manifest"]["belief_commitment_ref"] = "wrong"
    cases.append((d, S31IntegrityError, "commitment reference"))

    e = m01_inputs()
    e["variable_evolution_input_manifest"]["social_feature_ref"] = "wrong"
    cases.append((e, S31IntegrityError, "social_feature_panel"))

    for payload, error, message in cases:
        with pytest.raises(error, match=message):
            run_m01(payload)


def test_m01_accepts_empty_society_as_degraded():
    inputs = m01_inputs()
    inputs["validated_society_state_panel"]["records"] = []
    bundle = run_m01(inputs)
    society_ref = next(item for item in bundle["items"] if item["artifact_name"] == "validated_society_state_panel")
    assert society_ref["quality_status"] == "DEGRADED"
    assert bundle["quality_status"] == "DEGRADED"


def test_m02_rejects_missing_input_and_alignment_mismatches():
    bundle = run_m01()
    base = m01_inputs()
    payload = {
        "p9_evaluation_evidence_bundle": bundle,
        "phase4_social_handoff_manifest": base["phase4_social_handoff_manifest"],
        "variable_evolution_input_manifest": base["variable_evolution_input_manifest"],
        "phase3_run_snapshot": base["phase3_run_snapshot"],
    }
    missing = deepcopy(payload)
    del missing["phase3_run_snapshot"]
    with pytest.raises(S31ContractError, match="missing required inputs"):
        run_m02_wrapper(
            missing,
            {
                "execution_context": execution_context(),
                "p9_consumer_compatibility": compatibility_config(),
            },
        )

    context = execution_context()
    context["as_of_time"] = "2024-01-31T19:00:00Z"
    with pytest.raises(S31TemporalError, match="as_of_time"):
        run_m02(bundle=bundle, context=context)

    changed = deepcopy(base)
    changed["phase3_run_snapshot"]["pipeline_version"] = "OTHER"
    with pytest.raises(S31ContractError, match="pipeline_version"):
        run_m02(bundle=bundle, inputs=changed)

    changed = deepcopy(base)
    changed["variable_evolution_input_manifest"]["as_of_time"] = "2024-01-31T19:00:00Z"
    with pytest.raises(S31TemporalError, match="VariableEvolutionInputManifest.as_of_time"):
        run_m02(bundle=bundle, inputs=changed)


def test_m02_status_rollup_for_blocked_and_bound_consumers():
    blocked_bundle = run_m01()
    blocked_bundle["quality_status"] = "BLOCKED"
    blocked_bundle["quality_reasons"] = ["UPSTREAM_ARTIFACT_BLOCKED"]
    blocked_manifest = run_m02(bundle=blocked_bundle)
    assert blocked_manifest["quality_status"] == "BLOCKED"

    blocked_config = compatibility_config()
    blocked_config["consumer_binding_status"] = "BLOCKED"
    manifest = run_m02(compatibility=blocked_config)
    assert manifest["quality_status"] == "BLOCKED"
    assert "P9_CONSUMER_CONTRACT_BLOCKED" in manifest["quality_reasons"]

    bound_config = compatibility_config()
    bound_config["declared_p9_inputs"] = [
        "p9_evaluation_evidence_bundle",
        "p9_context_learning_handoff_manifest",
    ]
    bound_config["consumer_binding_status"] = "READY_FOR_BOUND_P9"
    manifest = run_m02(compatibility=bound_config)
    assert manifest["quality_status"] == "PASS"
    assert manifest["consumer_binding_status"] == "READY_FOR_BOUND_P9"
