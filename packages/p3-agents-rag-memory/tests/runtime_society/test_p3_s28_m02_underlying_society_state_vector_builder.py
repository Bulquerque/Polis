from __future__ import annotations
from pathlib import Path
import sys

_TESTS_ROOT = Path(__file__).resolve().parents[1]
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))

from copy import deepcopy
import pytest
from quant_pipeline.phase_03_agents_rag_memory.s28.entrypoints import run_m02
from s28_test_support import m02_inputs

def test_vector_has_exact_grain_and_families() -> None:
    record=run_m02(m02_inputs())["synthetic_society_state_panel"]["records"][0]
    assert (record["underlying_id"],record["proposition_id"],record["horizon"]) == ("PETR4","directional_outlook","5d")
    assert set(record["features"]) == {"belief","dynamics","attention","social","information","tag_projection"}
    assert record["status"] == "READY"

def test_s27_metrics_are_not_recalculated() -> None:
    value=m02_inputs(); value["belief_distribution_panel"]["records"][0]["belief_mean"]=.123
    record=run_m02(value)["synthetic_society_state_panel"]["records"][0]
    assert record["features"]["belief"]["belief_mean"] == .123

def test_missing_attention_is_material_degradation() -> None:
    value=m02_inputs(); value["attention_information_metrics"]["records"]=[]
    record=run_m02(value)["synthetic_society_state_panel"]["records"][0]
    assert record["status"] == "DEGRADED"
    assert record["features"]["attention"]["attention_intensity"] is None
    assert any(x["status"] == "MISSING" for x in record["family_statuses"])

def test_formula_version_mismatch_fails() -> None:
    value=m02_inputs(); value["aggregation_semantics_config"]["formula_version"]="other"
    with pytest.raises(Exception): run_m02(value)

def test_unbounded_metric_surface_rejected() -> None:
    value=m02_inputs(); value["emergence_vector_config"]["required_metric_paths"].append("arbitrary.feature")
    with pytest.raises(Exception): run_m02(value)
