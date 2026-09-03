"""P6.S4 mutation and deformation runner."""

from ..foundation.results import SubphaseResult
from .modules.P6_S4_M01_mutation_operator_registry import run as m01
from .modules.P6_S4_M02_local_mutation_engine import run as m02
from .modules.P6_S4_M03_mutation_trace_validator import run as m03
from .modules.P6_S4_M04_complexity_budget_gate import run as m04


def run_subphase(inputs, context, configuration):
    """Execute all mutation modules with a shared immutable context."""
    state = dict(inputs)
    results = []
    for runner in (m01, m02, m03, m04):
        result = runner(state, context, configuration)
        state.update(result.outputs)
        results.append(result)
    outputs = {
        key: value
        for result in results
        for key, value in result.outputs.items()
    }
    capability = (
        "AVAILABLE"
        if configuration.operational_mode.mutation_enabled
        else "UNAVAILABLE"
    )
    return SubphaseResult(
        subphase_id="P6.S4",
        module_results=tuple(results),
        outputs=outputs,
        capability_status=capability,
    )
