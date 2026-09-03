"""P6.S7 pricing, payoff, Greeks, and scenario runner."""
from ..foundation.results import SubphaseResult
from .modules.P6_S7_M01_entry_price_engine import run as m01
from .modules.P6_S7_M02_terminal_payoff_engine import run as m02
from .modules.P6_S7_M03_pathwise_valuation_engine import run as m03
from .modules.P6_S7_M04_greek_engine import run as m04
from .modules.P6_S7_M05_break_even_shape_engine import run as m05
from .modules.P6_S7_M06_scenario_evaluator import run as m06
from .modules.P6_S7_M07_ambiguity_evaluator import run as m07

def run_subphase(inputs,context,configuration):
 state=dict(inputs); results=[]
 for runner in (m01,m02,m03,m04,m05,m06,m07):
  result=runner(state,context,configuration); state.update(result.outputs); results.append(result)
 outputs={key:value for result in results for key,value in result.outputs.items()}
 return SubphaseResult(subphase_id="P6.S7",module_results=tuple(results),outputs=outputs)
