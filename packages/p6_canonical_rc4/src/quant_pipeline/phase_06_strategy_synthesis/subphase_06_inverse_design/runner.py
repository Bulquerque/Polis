"""P6.S6 inverse-design and solver-portfolio runner."""

from ..foundation.results import SubphaseResult
from .modules.P6_S6_M01_replication_basis_builder import run as m01
from .modules.P6_S6_M02_continuous_relaxation_solver import run as m02
from .modules.P6_S6_M03_mixed_integer_solver import run as m03
from .modules.P6_S6_M04_beam_search_solver import run as m04
from .modules.P6_S6_M05_local_search_solver import run as m05
from .modules.P6_S6_M06_evolutionary_challenger import run as m06
from .modules.P6_S6_M07_solver_portfolio_orchestrator import run as m07


def run_subphase(inputs, context, configuration):
    state = dict(inputs)
    results = []
    for runner in (m01, m02, m03, m04, m05, m06, m07):
        result = runner(state, context, configuration)
        state.update(result.outputs)
        results.append(result)
    outputs = {key: value for result in results for key, value in result.outputs.items()}
    status = "AVAILABLE" if configuration.operational_mode.inverse_design_enabled else "UNAVAILABLE"
    return SubphaseResult(subphase_id="P6.S6", module_results=tuple(results), outputs=outputs, capability_status=status)
