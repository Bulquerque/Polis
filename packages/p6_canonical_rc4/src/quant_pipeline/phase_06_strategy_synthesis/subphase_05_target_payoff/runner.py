"""P6.S5 target-payoff design runner."""

from ..foundation.results import SubphaseResult
from .modules.P6_S5_M01_market_implied_state_estimator import run as m01
from .modules.P6_S5_M02_belief_to_payoff_transformer import run as m02
from .modules.P6_S5_M03_target_payoff_regularizer import run as m03
from .modules.P6_S5_M04_target_payoff_qualification_gate import run as m04


def run_subphase(inputs, context, configuration):
    state = dict(inputs)
    results = []
    for runner in (m01, m02, m03, m04):
        result = runner(state, context, configuration)
        state.update(result.outputs)
        results.append(result)
    outputs = {key: value for result in results for key, value in result.outputs.items()}
    status = "AVAILABLE" if configuration.operational_mode.inverse_design_enabled else "UNAVAILABLE"
    return SubphaseResult(subphase_id="P6.S5", module_results=tuple(results), outputs=outputs, capability_status=status)
