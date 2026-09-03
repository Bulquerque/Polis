"""P6.S9 canonicalization and deterministic quality-diversity runner."""
from ..foundation.results import SubphaseResult
from .modules.P6_S9_M01_leg_canonicalizer import run as m01
from .modules.P6_S9_M02_relative_scale_normalizer import run as m02
from .modules.P6_S9_M03_payoff_fingerprint_builder import run as m03
from .modules.P6_S9_M04_economic_fingerprint_builder import run as m04
from .modules.P6_S9_M05_equivalence_clustering import run as m05
from .modules.P6_S9_M06_representative_selector import run as m06

def run_subphase(inputs,context,configuration):
 state=dict(inputs); results=[]
 for runner in (m01,m02,m03,m04,m05,m06):
  result=runner(state,context,configuration); state.update(result.outputs); results.append(result)
 outputs={key:value for result in results for key,value in result.outputs.items()}
 return SubphaseResult(subphase_id="P6.S9",module_results=tuple(results),outputs=outputs)
