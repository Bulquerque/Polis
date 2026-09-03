"""P6.S1 boundary and PIT snapshot runner."""

from __future__ import annotations

from ..foundation.context import PhaseContext
from ..foundation.results import SubphaseResult
from .modules.P6_S1_M01_p5_belief_handoff_validator import run as run_m01
from .modules.P6_S1_M02_option_market_input_validator import run as run_m02
from .modules.P6_S1_M03_underlying_market_input_validator import run as run_m03
from .modules.P6_S1_M04_static_arbitrage_diagnostic import run as run_m04
from .modules.P6_S1_M05_pit_market_snapshot_builder import run as run_m05


def run_subphase(inputs, context: PhaseContext, configuration=None) -> SubphaseResult:
    state = dict(inputs)
    results = []
    for runner in (run_m01, run_m02, run_m03, run_m04, run_m05):
        result = runner(state, context, configuration) if runner is run_m01 else runner(state, context)
        state.update(result.outputs)
        results.append(result)
    outputs = {key: value for result in results for key, value in result.outputs.items()}
    return SubphaseResult(subphase_id="P6.S1", module_results=tuple(results), outputs=outputs)
