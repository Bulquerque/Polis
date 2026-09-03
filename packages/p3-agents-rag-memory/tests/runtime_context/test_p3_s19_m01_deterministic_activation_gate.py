from quant_pipeline.phase_03_agents_rag_memory.s19.models import ExecutionStatus
from quant_pipeline.phase_03_agents_rag_memory.s19.service import run_s19
from .s19_test_support import load_inputs


def test_m01_activation_fixture(plan_root) -> None:
    inputs, config = load_inputs(plan_root)
    result = run_s19(inputs, config)
    assert result.activation_panel.status is ExecutionStatus.DEGRADED
    assert len(result.activation_panel.records) == 2
