from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.m05_distributional_ambiguity_and_worst_case_engine import (
    evaluate_distributional_robustness,
)


def test_scenario_budget_is_fail_closed(full_request):
    distribution = full_request.dro.distribution
    many = distribution.model_copy(
        update={
            "scenario_ids": tuple(f"s{i}" for i in range(81)),
            "state_vectors": tuple((float(i),) for i in range(81)),
            "losses": tuple(float(i) for i in range(81)),
            "scores": None,
        }
    )
    result = evaluate_distributional_robustness(
        full_request.dro.model_copy(update={"distribution": many})
    )
    assert result.status is S6State.CAPABILITY_UNAVAILABLE
