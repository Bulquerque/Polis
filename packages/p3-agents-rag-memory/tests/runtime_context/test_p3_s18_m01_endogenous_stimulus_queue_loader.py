from __future__ import annotations

import copy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.s18.errors import S18TemporalViolationError
from quant_pipeline.phase_03_agents_rag_memory.s18.hashing import sha256_hex
from quant_pipeline.phase_03_agents_rag_memory.s18.queue_loader import (
    load_endogenous_stimulus_queue,
)

from .s18_test_support import deep_copy_inputs


def m01_inputs(all_inputs: dict[str, object]) -> dict[str, object]:
    return {
        "prior_cycle_endogenous_stimulus_queue": all_inputs[
            "prior_cycle_endogenous_stimulus_queue"
        ],
        "phase3_run_snapshot": all_inputs["phase3_run_snapshot"],
        "stimulus_event_bus_config": all_inputs["stimulus_event_bus_config"],
    }


def test_m01_loads_prior_cycle_queue(plan_root) -> None:
    result = load_endogenous_stimulus_queue(m01_inputs(deep_copy_inputs(plan_root)))
    assert result.status.value == "READY"
    assert len(result.items) == 1
    assert len(result.consumption_ledger) == 1
    consumption = result.consumption_ledger[0]
    assert consumption.produced_in_cycle == "cycle:test-prior"
    assert consumption.available_from_cycle == result.cycle_id
    assert consumption.consumed_in_cycle == result.cycle_id
    assert consumption.decision.value == "ACCEPTED"


def test_m01_consumption_ledger_is_deterministic(plan_root) -> None:
    inputs = m01_inputs(deep_copy_inputs(plan_root))
    first = load_endogenous_stimulus_queue(inputs)
    second = load_endogenous_stimulus_queue(copy.deepcopy(inputs))
    assert first.consumption_ledger == second.consumption_ledger
    assert first.content_hash == second.content_hash


def test_m01_fails_on_same_cycle_event(plan_root) -> None:
    values = deep_copy_inputs(plan_root)
    queue = values["prior_cycle_endogenous_stimulus_queue"]
    snapshot = values["phase3_run_snapshot"]
    queue["source_cycle_id"] = snapshot["cycle_id"]
    queue["items"][0]["created_cycle_id"] = snapshot["cycle_id"]
    queue.pop("content_hash")
    queue["content_hash"] = sha256_hex(queue)
    with pytest.raises(S18TemporalViolationError):
        load_endogenous_stimulus_queue(m01_inputs(values))
