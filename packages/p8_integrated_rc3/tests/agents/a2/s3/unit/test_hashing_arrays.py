import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.arrays import ScenarioSet
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.hashing import canonical_sha256


def test_canonical_hash_dict_order():
    assert canonical_sha256({"a":1,"b":2}) == canonical_sha256({"b":2,"a":1})


def test_scenario_probability_must_close():
    with pytest.raises(Exception):
        ScenarioSet(values=np.zeros((2,1,1)), probabilities=np.array([0.4,0.4]), scenario_ids=("a","b"), factor_ids=("x",), step_labels=("t",), origins=("m","m"))


def test_scenario_roundtrip(tmp_path):
    original = ScenarioSet(values=np.arange(6).reshape(3,1,2), probabilities=np.array([0.2,0.3,0.5]), scenario_ids=("a","b","c"), factor_ids=("x","y"), step_labels=("t",), origins=("m","m","h"))
    path=tmp_path/"s.npz"; original.save_npz(path)
    loaded=ScenarioSet.load_npz(path)
    assert loaded.content_sha256()==original.content_sha256()
