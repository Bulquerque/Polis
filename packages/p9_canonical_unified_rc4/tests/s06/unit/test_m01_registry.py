from datetime import timedelta

from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.m01_stress_scenario_taxonomy_and_commitment_registry import (
    build_scenario_registry,
)


def test_registry_commits_and_covers_material_risk(scenario_request):
    result = build_scenario_registry(scenario_request)
    assert result.status is S6State.COMMITTED
    assert result.weighted_material_risk_coverage == 1.0
    assert len(result.scenarios) == 1


def test_duplicate_scenario_is_rejected(scenario_request):
    proposal = scenario_request.proposals[0]
    duplicate = proposal.model_copy(update={"scenario_id": "duplicate"})
    result = build_scenario_registry(
        scenario_request.model_copy(update={"proposals": (proposal, duplicate)})
    )
    assert result.duplicate_scenario_ids == ("duplicate",)
    assert "P9_STRESS_SCENARIO_DUPLICATE" in result.reason_codes


def test_post_outcome_scenario_is_rejected(scenario_request):
    observed = scenario_request.context.decision_time - timedelta(days=1)
    late = scenario_request.proposals[0].model_copy(update={"created_at": observed})
    result = build_scenario_registry(
        scenario_request.model_copy(
            update={"proposals": (late,), "outcome_results_observed_at": observed}
        )
    )
    assert result.status is S6State.INVALID
    assert "P9_STRESS_SCENARIO_POST_OUTCOME" in result.reason_codes
