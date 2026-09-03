"""P6.S2 canonical strategy domain runner."""
from ..foundation.results import SubphaseResult
from .modules.P6_S2_M01_contract_existence_gate import run as m01
from .modules.P6_S2_M02_strategy_grammar_registry import run as m02
from .modules.P6_S2_M03_objective_family_registry import run as m03
from .modules.P6_S2_M04_constraint_policy_registry import run as m04
from .modules.P6_S2_M05_strategy_identity_builder import run as m05

def run_subphase(inputs, context, configuration):
    state=dict(inputs); results=[]
    for runner in (m01,m02,m03,m04,m05):
        result=runner(state,context,configuration); state.update(result.outputs); results.append(result)
    outputs={key:value for result in results for key,value in result.outputs.items()}
    return SubphaseResult(subphase_id="P6.S2",module_results=tuple(results),outputs=outputs)
