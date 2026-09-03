from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.m05_distributional_ambiguity_and_worst_case_engine import (
    evaluate_distributional_robustness,
)


def test_radius_zero_reconciles_and_risk_is_monotone(full_request):
    result = evaluate_distributional_robustness(full_request.dro)
    assert result.status is S6State.QUALIFIED
    assert abs(result.frontier[0].worst_case_mean_loss - result.empirical_mean_loss) < 1e-8
    losses = [point.worst_case_mean_loss for point in result.frontier]
    assert losses == sorted(losses)


def test_uncalibrated_radius_is_research_only(full_request):
    policy = full_request.dro.policy.model_copy(update={"radius_calibration_id": None})
    result = evaluate_distributional_robustness(full_request.dro.model_copy(update={"policy": policy}))
    assert result.status is S6State.RESEARCH_ONLY
    assert "P9_STRESS_DRO_RADIUS_UNCALIBRATED" in result.reason_codes
