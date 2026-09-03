from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.s31_products import S31ContractError, S31TemporalError
from .s31_support import execution_context, m01_inputs, run_m01, run_m02


@pytest.mark.parametrize(
    "missing",
    [
        "phase4_social_handoff_manifest",
        "variable_evolution_input_manifest",
        "belief_outcome_commitment_log",
        "model_knowledge_cutoff_report",
        "phase3_run_snapshot",
        "validated_society_state_panel",
    ],
)
def test_m01_rejects_each_missing_input(missing):
    inputs = m01_inputs()
    del inputs[missing]
    with pytest.raises(S31ContractError, match="missing required inputs"):
        run_m01(inputs)


def test_m01_rejects_pipeline_version_mismatch():
    inputs = m01_inputs()
    inputs["phase3_run_snapshot"]["pipeline_version"] = "INCOMPATIBLE"
    with pytest.raises(S31ContractError, match="pipeline_version"):
        run_m01(inputs)


def test_m01_rejects_context_as_of_mismatch():
    context = execution_context()
    context["as_of_time"] = "2024-01-31T19:00:00Z"
    with pytest.raises(S31TemporalError, match="as_of_time"):
        run_m01(context=context)


def test_m02_rejects_bundle_run_mismatch():
    bundle = run_m01()
    bundle["run_id"] = "other-run"
    with pytest.raises(S31ContractError, match="run_id"):
        run_m02(bundle=bundle)


def test_strict_models_reject_unknown_input_fields():
    inputs = m01_inputs()
    inputs["phase3_run_snapshot"]["unknown_field"] = "x"
    with pytest.raises(S31ContractError, match="extra_forbidden"):
        run_m01(inputs)
