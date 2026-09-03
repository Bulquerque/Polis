from __future__ import annotations
from pathlib import Path
import sys

_TESTS_ROOT = Path(__file__).resolve().parents[1]
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))

from copy import deepcopy
import pytest
from quant_pipeline.phase_03_agents_rag_memory.s28.entrypoints import run_m03
from s28_test_support import m03_inputs

def test_quality_is_derived_not_constant() -> None:
    base=run_m03(m03_inputs())["validated_society_state_panel"]["records"][0]["quality"]
    value=m03_inputs(); value["source_quality_panel"]["records"][0]["quality_score"]=.4
    value["source_quality_panel"]["records"][0]["completeness"]=.4
    changed=run_m03(value)["validated_society_state_panel"]["records"][0]["quality"]
    assert changed["quality_score"] < base["quality_score"]
    assert changed["status"] == "BLOCKED"

def test_low_coverage_blocks() -> None:
    value=m03_inputs(); rec=value["synthetic_society_state_panel"]["records"][0]
    rec["coverage"]["population_coverage_ratio"]=.1
    rec["coverage"]["belief_coverage_ratio"]=.1
    quality=run_m03(value)["validated_society_state_panel"]["records"][0]["quality"]
    assert quality["status"] == "BLOCKED"

def test_features_are_preserved() -> None:
    value=m03_inputs(); expected=deepcopy(value["synthetic_society_state_panel"]["records"][0]["features"])
    expected["dynamics"]["applicability"]="APPLICABLE"
    expected["information"]["expert_nonexpert_applicability"]="APPLICABLE"
    expected["information"]["institutional_applicability"]="APPLICABLE"
    output=run_m03(value)["validated_society_state_panel"]["records"][0]
    assert output["features"] == expected

def test_missing_source_quality_is_material() -> None:
    value=m03_inputs(); value["source_quality_panel"]["records"].pop()
    quality=run_m03(value)["validated_society_state_panel"]["records"][0]["quality"]
    assert quality["status"] == "BLOCKED"
    assert any(i["code"] == "SOURCE_QUALITY_MISSING" for i in quality["issues"])

def test_context_mismatch_fails() -> None:
    value=m03_inputs(); value["phase3_run_snapshot"]["cycle_id"]=8
    with pytest.raises(Exception): run_m03(value)

def test_genesis_dynamics_do_not_reduce_metric_completeness() -> None:
    value=m03_inputs(); rec=value["synthetic_society_state_panel"]["records"][0]
    rec["features"]["dynamics"]={
        "belief_update_velocity_per_day": None,
        "belief_reversal_rate": None,
        "applicability": "NOT_APPLICABLE_GENESIS",
    }
    quality=run_m03(value)["validated_society_state_panel"]["records"][0]["quality"]
    assert quality["metric_completeness"] == 1.0
    assert not any(issue["code"].startswith("METRIC_COMPLETENESS") for issue in quality["issues"])
