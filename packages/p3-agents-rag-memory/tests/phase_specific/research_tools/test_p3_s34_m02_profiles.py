from __future__ import annotations

from copy import deepcopy
import pytest

from .support_s34 import build_s34_m02, person_inputs
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError


def _scores(output, person_id: str) -> dict[str, float]:
    return {r["capability_id"]: r["score"] for r in output["person_research_capability_panel"]["records"] if r["person_id"] == person_id}


def test_profiles_are_ex_ante_explainable_and_complete() -> None:
    out = build_s34_m02()
    coverage = out["capability_profile_coverage_report"]
    assert coverage["coverage_ratio"] == 1.0
    assert coverage["forbidden_source_fields_detected"] == []
    assert out["person_research_capability_panel"]["person_count"] == 2
    assert all(record["components"] for record in out["person_research_capability_panel"]["records"])


def test_institutional_person_has_deeper_capabilities_than_retail() -> None:
    out = build_s34_m02()
    retail = _scores(out, "retail-1")
    institutional = _scores(out, "institutional-1")
    for capability in ("document_search", "forensic_review", "quantitative_statistics", "valuation"):
        assert institutional[capability] > retail[capability]
    assert institutional["professional_data_access"] == 1.0
    assert retail["professional_data_access"] == 0.0


def test_future_or_performance_fields_fail_closed() -> None:
    inputs = person_inputs()
    poisoned = deepcopy(inputs["validated_population_manifest"])
    poisoned["population_manifest"]["persons"][0]["profile"]["future_return"] = 0.75
    with pytest.raises(ResearchToolContractError) as exc:
        build_s34_m02({"validated_population_manifest": poisoned})
    assert exc.value.reason_code == "P3RT-AUTH-3411"


def test_profile_hash_is_deterministic() -> None:
    assert build_s34_m02()["person_research_capability_panel"]["content_hash"] == build_s34_m02()["person_research_capability_panel"]["content_hash"]
