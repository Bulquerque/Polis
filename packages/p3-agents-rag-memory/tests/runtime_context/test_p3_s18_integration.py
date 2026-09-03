from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.s18.service import run_subphase

from .s18_test_support import deep_copy_inputs


def test_s17_to_s18_canonical_handoff(plan_root) -> None:
    result = run_subphase(deep_copy_inputs(plan_root))
    assert result.endogenous_stimulus_stream.status.value == "READY"
    assert len(result.stimulus_panel.records) == 2
    assert all(
        record.target_cycle_id == "cycle:test"
        for record in result.stimulus_panel.records
    )
