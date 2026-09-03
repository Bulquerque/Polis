from __future__ import annotations
import pytest
from quant_pipeline.phase_03_agents_rag_memory.contracts import canonical_json as _canonical_json

@pytest.mark.parametrize('value',[{'a':1,'b':2},{'z':0,'a':-1,'m':9},{'alpha':1},{'x':1,'y':2,'w':3}])
def test_canonical_json_is_independent_of_dict_insertion_order(value:dict[str,int])->None:
    assert _canonical_json(value)==_canonical_json(dict(reversed(list(value.items()))))
