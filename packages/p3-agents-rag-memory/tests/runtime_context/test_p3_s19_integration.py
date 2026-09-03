from quant_pipeline.phase_03_agents_rag_memory.s19.service import run_s19
from .s19_test_support import load_inputs


def test_s18_to_s19_handoff(plan_root) -> None:
    inputs, config = load_inputs(plan_root)
    result = run_s19(inputs, config)
    assert result.activation_panel.run_id == inputs["stimulus_panel"]["run_id"]
    assert result.cognitive_cycle_schedule.metrics.total_step_count == 3
