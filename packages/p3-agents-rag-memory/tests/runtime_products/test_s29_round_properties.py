from __future__ import annotations
import pytest
from quant_pipeline.phase_03_agents_rag_memory.s29_products import _round

@pytest.mark.parametrize('value',[0.0,0.000000000001,0.1,0.3333333333333,0.5,0.999999999999,1.0])
def test_round_always_stays_bounded(value:float)->None:
    result=_round(value,12)
    assert 0.0<=result<=1.0
