from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from collections.abc import Mapping
from typing import Any

from ..contracts import ModuleExecutionContext
from ..foundation.warmup_memory.replay.canonical_replay import (
    CanonicalReplayLeakageValidator,
    is_canonical_replay,
)
from ..foundation.warmup_memory.replay.service import BootstrapLeakageGuard

MODULE_ID = "P3.S11.M02"
MODULE_NAME = "bootstrap_leakage_guard"
SUBPHASE = "P3.S11"
LEGACY_ENTRYPOINT_DEPRECATED = True
CONTRACT = "modules/P3_S11_M02_bootstrap_leakage_guard.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "initial_cycle_state_snapshot",
    "validated_warmup_history",
    "warmup_replay_audit",
)
PRODUCED_OUTPUTS = ("validated_initial_cycle_state_snapshot",)


@deprecated_legacy_entrypoint("P3.S11.M02")
def run_module(inputs: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deprecated compatibility entrypoint; new callers must use ``execute``."""
    context = context or {}
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise ValueError(f"P3.S11.M02 missing inputs: {missing}")
    snapshot = inputs["initial_cycle_state_snapshot"]
    if is_canonical_replay(snapshot):
        validated = CanonicalReplayLeakageValidator().validate(
            snapshot,
            inputs["warmup_replay_audit"],
            context,
        )
        return {"validated_initial_cycle_state_snapshot": validated}
    service = context.get("bootstrap_leakage_guard") or BootstrapLeakageGuard()
    result = service.validate(**{name: inputs[name] for name in REQUIRED_INPUTS})
    return {"validated_initial_cycle_state_snapshot": result.model_dump(mode="json")}


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))
