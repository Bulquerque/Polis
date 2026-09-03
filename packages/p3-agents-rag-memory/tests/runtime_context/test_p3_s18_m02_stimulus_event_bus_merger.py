from __future__ import annotations

import copy

from quant_pipeline.phase_03_agents_rag_memory.s18.event_bus import merge_stimulus_event_bus
from quant_pipeline.phase_03_agents_rag_memory.s18.queue_loader import (
    load_endogenous_stimulus_queue,
)

from .s18_test_support import deep_copy_inputs


def build_m02_inputs(values: dict[str, object]) -> dict[str, object]:
    endogenous = load_endogenous_stimulus_queue(
        {
            "prior_cycle_endogenous_stimulus_queue": values[
                "prior_cycle_endogenous_stimulus_queue"
            ],
            "phase3_run_snapshot": values["phase3_run_snapshot"],
            "stimulus_event_bus_config": values["stimulus_event_bus_config"],
        }
    )
    return {
        "resolved_external_stimulus_stream": values[
            "resolved_external_stimulus_stream"
        ],
        "endogenous_stimulus_stream": endogenous.model_dump(mode="json"),
        "stimulus_event_bus_config": values["stimulus_event_bus_config"],
    }


def test_m02_merges_s17_and_prior_cycle_streams(plan_root) -> None:
    result = merge_stimulus_event_bus(build_m02_inputs(deep_copy_inputs(plan_root)))
    assert len(result.records) == 2
    assert {record.origin_type.value for record in result.records} == {
        "EXTERNAL_PIT_CONTEXT",
        "ATTENTION_FOLLOWUP",
    }


def test_m02_is_deterministic(plan_root) -> None:
    values = deep_copy_inputs(plan_root)
    first = merge_stimulus_event_bus(build_m02_inputs(values)).model_dump(mode="json")
    second = merge_stimulus_event_bus(
        build_m02_inputs(copy.deepcopy(values))
    ).model_dump(mode="json")
    assert first == second
