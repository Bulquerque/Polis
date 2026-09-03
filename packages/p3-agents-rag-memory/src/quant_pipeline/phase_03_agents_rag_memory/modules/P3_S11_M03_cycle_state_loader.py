from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from collections.abc import Mapping
from typing import Any

from ..contracts import ModuleExecutionContext
from ..foundation.warmup_memory.replay.canonical_replay import (
    CanonicalReplayStateLoader,
    is_canonical_replay,
)
from ..foundation.warmup_memory.replay.service import CycleStateLoader

MODULE_ID = "P3.S11.M03"
MODULE_NAME = "cycle_state_loader"
SUBPHASE = "P3.S11"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S11_M03_cycle_state_loader.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = ("validated_initial_cycle_state_snapshot", "prior_cycle_state_snapshot")
PRODUCED_OUTPUTS = (
    "current_person_state_panel",
    "current_belief_state_panel",
    "current_memory_state",
    "current_social_graph",
)


@deprecated_legacy_entrypoint("P3.S11.M03")
def run_module(inputs: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deprecated compatibility entrypoint; new callers must use ``execute``."""
    context = context or {}
    candidate = inputs.get("prior_cycle_state_snapshot") or inputs.get("validated_initial_cycle_state_snapshot")
    if is_canonical_replay(candidate):
        return CanonicalReplayStateLoader().load(candidate, context)
    service = context.get("cycle_state_loader") or CycleStateLoader()
    request = {
        "current_run_id": context["current_run_id"],
        "current_snapshot_id": context["current_snapshot_id"],
        "current_cycle_id": context["current_cycle_id"],
        "current_cycle_number": context["current_cycle_number"],
        "current_as_of": context["current_as_of"],
        "validated_initial_cycle_state_snapshot": inputs.get("validated_initial_cycle_state_snapshot"),
        "prior_cycle_state_snapshot": inputs.get("prior_cycle_state_snapshot"),
    }
    result = service.load(request)
    return {
        "current_person_state_panel": result.person_state.model_dump(mode="json"),
        "current_belief_state_panel": result.belief_state.model_dump(mode="json"),
        "current_memory_state": result.memory_state.model_dump(mode="json"),
        "current_social_graph": result.social_graph.model_dump(mode="json"),
    }


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))
