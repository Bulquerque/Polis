from __future__ import annotations
import pytest
from .s31_support import m01_inputs, run_m01

@pytest.mark.parametrize('risk',['STRICT_CLEAN','LOWER_RISK','UNKNOWN','CONTAMINATION_RISK'])
def test_cutoff_status_is_always_material(risk:str)->None:
    inputs=m01_inputs(); inputs['model_knowledge_cutoff_report']['risk_class']=risk
    bundle=run_m01(inputs)
    assert bundle['quality_status'] in {'PASS','DEGRADED','BLOCKED'}
