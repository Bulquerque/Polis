from __future__ import annotations
from pathlib import Path
import sys

_TESTS_ROOT = Path(__file__).resolve().parents[1]
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))

from copy import deepcopy
import pytest
from quant_pipeline.phase_03_agents_rag_memory.s28.entrypoints import run_m01
from s28_test_support import m01_inputs

def test_projection_matches_expected_cohorts() -> None:
    panel=run_m01(m01_inputs())["tag_projection_panel"]
    by_tag={r["tag_id"]:r for r in panel["records"]}
    assert by_tag["research_skilled"]["belief_mean"] == pytest.approx(.6)
    assert by_tag["intuitive"]["belief_mean"] == pytest.approx(-.4)
    assert by_tag["risk_averse"]["status"] == "SUPPRESSED_SMALL_COHORT"
    assert by_tag["risk_averse"]["belief_mean"] is None
    summary=panel["summaries"][0]
    assert summary["expert_nonexpert_divergence"] == pytest.approx(1.0)
    assert summary["institutional_disagreement"] == pytest.approx(.5)

def test_single_institution_cohort_is_not_applicable_not_degraded() -> None:
    value=m01_inputs()
    for panel in ("person_seed_panel", "validated_population_manifest"):
        for record in value[panel]["records"]:
            record["institution_type"]="single_cohort"
    summary=run_m01(value)["tag_projection_panel"]["summaries"][0]
    assert summary["status"] == "READY"
    assert summary["institutional_disagreement"] is None
    assert summary["institutional_applicability"] == "NOT_APPLICABLE_INSUFFICIENT_COHORTS"

def test_output_contains_no_person_ids() -> None:
    assert "person_id" not in str(run_m01(m01_inputs()))

def test_unknown_tag_fails_closed() -> None:
    value=m01_inputs(); value["person_seed_panel"]["records"][0]["tags"][0]["tag_id"]="unknown"
    with pytest.raises(Exception): run_m01(value)

def test_person_join_mismatch_fails() -> None:
    value=m01_inputs(); value["validated_population_manifest"]["records"].pop()
    with pytest.raises(Exception): run_m01(value)

def test_future_belief_fails() -> None:
    value=m01_inputs(); value["next_belief_state_panel"]["records"][0]["changed_at"]="2027-01-01T00:00:00Z"
    with pytest.raises(Exception): run_m01(value)
