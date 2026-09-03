from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.s17.service import run_subphase
from .s17_test_support import deep_copy_inputs


def test_s17_runs_canonical_two_module_handoff(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    first = run_subphase(inputs).model_dump(mode="python")
    second = run_subphase(inputs).model_dump(mode="python")
    assert first == second
    assert first["external_stimulus_stream"]["status"] == "READY"
    assert first["resolved_external_stimulus_stream"]["status"] == "READY"
    assert (
        first["resolved_external_stimulus_stream"]["items"][0]["selected_underlying_id"]
        == "figi:BBG000B9XRY4"
    )
