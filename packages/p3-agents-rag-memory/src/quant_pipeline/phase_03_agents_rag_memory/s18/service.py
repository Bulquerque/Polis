from __future__ import annotations

from typing import Any, Mapping

from .event_bus import merge_stimulus_event_bus, merge_stimulus_event_bus_exactly_once
from .models import SubphaseS18Result
from .queue_loader import load_endogenous_stimulus_queue


def run_subphase(inputs: Mapping[str, Any], *, exactly_once_ledger=None) -> SubphaseS18Result:
    """Run P3.S18.M01 and P3.S18.M02 in canonical order."""

    endogenous = load_endogenous_stimulus_queue(
        {
            "prior_cycle_endogenous_stimulus_queue": inputs[
                "prior_cycle_endogenous_stimulus_queue"
            ],
            "phase3_run_snapshot": inputs["phase3_run_snapshot"],
            "stimulus_event_bus_config": inputs["stimulus_event_bus_config"],
        }
    )
    merger = merge_stimulus_event_bus if exactly_once_ledger is None else (
        lambda payload: merge_stimulus_event_bus_exactly_once(payload, exactly_once_ledger)
    )
    panel = merger(
        {
            "resolved_external_stimulus_stream": inputs[
                "resolved_external_stimulus_stream"
            ],
            "endogenous_stimulus_stream": endogenous.model_dump(mode="python"),
            "stimulus_event_bus_config": inputs["stimulus_event_bus_config"],
        }
    )
    return SubphaseS18Result(
        endogenous_stimulus_stream=endogenous,
        stimulus_panel=panel,
    )
