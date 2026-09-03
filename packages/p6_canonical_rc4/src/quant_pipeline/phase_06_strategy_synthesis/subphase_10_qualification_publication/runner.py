"""P6.S10 qualification and publication runner."""

from __future__ import annotations

from typing import Any

from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult, SubphaseResult
from .modules.P6_S10_M01_canonical_strategy_publisher import run as run_canonical
from .modules.P6_S10_M02_p7_v1_projection_builder import run as run_legacy
from .modules.P6_S10_M03_phase7_handoff_manifest_builder import run as run_handoff


def run_subphase(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration: Any,
) -> SubphaseResult:
    """Execute the three official publication modules in contract order."""
    state = dict(inputs)
    results: list[ModuleResult] = []

    canonical = run_canonical(state, context, configuration)
    state.update(canonical.outputs)
    results.append(canonical)
    if configuration.publication.publish_legacy_p7_projection:
        legacy = run_legacy(state, context, configuration)
        state.update(legacy.outputs)
        results.append(legacy)
    handoff = run_handoff(state, context, configuration)
    state.update(handoff.outputs)
    results.append(handoff)

    outputs = {
        name: artifact
        for result in results
        for name, artifact in result.outputs.items()
    }
    outputs["quality_diversity_archive"] = state["quality_diversity_archive"]
    outputs["strategy_market_snapshot"] = state["strategy_market_snapshot"]
    return SubphaseResult(
        subphase_id="P6.S10",
        module_results=tuple(results),
        outputs=outputs,
    )
