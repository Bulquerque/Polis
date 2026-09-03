from __future__ import annotations

from copy import deepcopy
import random

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S29_M01_agent_disagreement_panel_builder import (
    run_module as run_m01,
)


def test_random_record_permutations_preserve_output(
    m01_inputs: dict,
    execution_context: dict,
) -> None:
    baseline = run_m01(m01_inputs, execution_context)["outputs"]["agent_disagreement_panel"]
    rng = random.Random(20260728)
    for _ in range(50):
        candidate = deepcopy(m01_inputs)
        rng.shuffle(candidate["belief_distribution_panel"]["records"])
        rng.shuffle(candidate["validated_society_state_panel"]["records"])
        output = run_m01(candidate, execution_context)["outputs"]["agent_disagreement_panel"]
        assert output == baseline


def test_disagreement_and_agreement_are_complements_when_computable(
    m01_inputs: dict,
    execution_context: dict,
) -> None:
    output = run_m01(m01_inputs, execution_context)["outputs"]["agent_disagreement_panel"]
    for record in output["records"]:
        if record["disagreement_score"] is not None:
            assert round(record["disagreement_score"] + record["agent_agreement_score"], 12) == 1.0
