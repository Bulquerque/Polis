"""P6.S8 feasibility and defined-risk runner."""
from ..foundation.results import SubphaseResult
from .modules.P6_S8_M01_structural_validator import run as m01
from .modules.P6_S8_M02_maximum_loss_prover import run as m02
from .modules.P6_S8_M03_margin_feasibility_gate import run as m03
from .modules.P6_S8_M04_liquidity_gate import run as m04
from .modules.P6_S8_M05_cost_gate import run as m05
from .modules.P6_S8_M06_data_quality_gate import run as m06
from .modules.P6_S8_M07_economic_sanity_gate import run as m07

def run_subphase(inputs,context,configuration):
 state=dict(inputs); results=[]
 for runner in (m01,m02,m03,m04,m05,m06,m07):
  result=runner(state,context,configuration); state.update(result.outputs); results.append(result)
 outputs={key:value for result in results for key,value in result.outputs.items()}
 return SubphaseResult(subphase_id="P6.S8",module_results=tuple(results),outputs=outputs)
