from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    BreachDirection,
    OutputSemantics,
    S6State,
    SeedPolicy,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.m07_reverse_stress_breakpoint_and_resilience_engine import (
    solve_reverse_stress,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    FactorBound,
    FailureCondition,
    QuadraticResponseModel,
    ReverseStressRequest,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import ReverseStressPolicy


def test_linear_reverse_stress_matches_analytic_solution(context):
    model = QuadraticResponseModel(
        model_id="linear-loss",
        factor_ids=("x",),
        units=("unit",),
        baseline_value=0.0,
        linear_coefficients=(-1.0,),
        quadratic_matrix=((0.0,),),
        semantics=OutputSemantics.PNL,
        model_sha256=content_sha256({"linear": -1.0}),
    )
    result = solve_reverse_stress(
        ReverseStressRequest(
            context=context,
            response_model=model,
            bounds=(FactorBound(factor_id="x", lower=-2.0, upper=2.0),),
            failure_condition=FailureCondition(
                condition_id="limit",
                threshold=-1.0,
                breach_direction=BreachDirection.LESS_THAN_OR_EQUAL,
            ),
            seed_policy=SeedPolicy(root_entropy=7),
            policy=ReverseStressPolicy(minimum_safe_distance=0.5),
        )
    )
    assert result.status is S6State.STRESS_RESILIENT
    assert abs(result.distance_to_failure - 1.0) < 1e-5
    assert abs(dict(result.shock_vector)["x"] - 1.0) < 1e-5


def test_no_failure_in_domain_is_valid(context):
    model = QuadraticResponseModel(
        model_id="safe",
        factor_ids=("x",),
        units=("unit",),
        baseline_value=0.0,
        linear_coefficients=(0.0,),
        quadratic_matrix=((0.0,),),
        semantics=OutputSemantics.PNL,
        model_sha256=content_sha256({"safe": True}),
    )
    result = solve_reverse_stress(
        ReverseStressRequest(
            context=context,
            response_model=model,
            bounds=(FactorBound(factor_id="x", lower=-1.0, upper=1.0),),
            failure_condition=FailureCondition(
                condition_id="limit",
                threshold=-1.0,
                breach_direction=BreachDirection.LESS_THAN_OR_EQUAL,
            ),
            seed_policy=SeedPolicy(root_entropy=8),
        )
    )
    assert result.status is S6State.NO_FAILURE_WITHIN_DOMAIN
