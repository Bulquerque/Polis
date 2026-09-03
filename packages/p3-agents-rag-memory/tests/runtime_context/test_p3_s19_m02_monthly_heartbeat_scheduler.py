from quant_pipeline.phase_03_agents_rag_memory.s19.models import TriggerType
from quant_pipeline.phase_03_agents_rag_memory.s19.service import run_s19
from .s19_test_support import load_inputs


def test_m02_event_and_heartbeat_schedule(plan_root) -> None:
    inputs, config = load_inputs(plan_root)
    result = run_s19(inputs, config)
    assert [step.trigger_type for step in result.cognitive_cycle_schedule.steps] == [
        TriggerType.STIMULUS, TriggerType.STIMULUS, TriggerType.HEARTBEAT
    ]
