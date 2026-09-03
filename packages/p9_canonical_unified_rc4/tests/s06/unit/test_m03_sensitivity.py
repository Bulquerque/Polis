from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    OutputSemantics,
    S6State,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.m01_stress_scenario_taxonomy_and_commitment_registry import (
    build_scenario_registry,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.m03_factor_shock_and_global_sensitivity_surface_engine import (
    build_sensitivity_surface,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    FactorAxis,
    QuadraticResponseModel,
    SensitivitySurfaceRequest,
)


def test_linear_surface_recovers_gradient(context, scenario_request):
    registry = build_scenario_registry(scenario_request)
    model = QuadraticResponseModel(
        model_id="linear",
        factor_ids=("equity",),
        units=("decimal",),
        baseline_value=2.0,
        linear_coefficients=(3.0,),
        quadratic_matrix=((0.0,),),
        semantics=OutputSemantics.PNL,
        model_sha256=content_sha256({"linear": 3.0}),
    )
    result = build_sensitivity_surface(
        SensitivitySurfaceRequest(
            context=context,
            registry=registry,
            response_model=model,
            axes=(FactorAxis(factor_id="equity", grid_values=(-1.0, 0.0, 1.0)),),
        )
    )
    assert result.status is S6State.SUCCESS
    assert result.factor_sensitivities[0].local_gradient == 3.0
    values = [point.output_value for point in result.points]
    assert values == [-1.0, 2.0, 5.0]


def test_known_interaction_is_reported(context, scenario_request, response_model):
    registry = build_scenario_registry(scenario_request)
    result = build_sensitivity_surface(
        SensitivitySurfaceRequest(
            context=context,
            registry=registry,
            response_model=response_model,
            axes=(
                FactorAxis(factor_id="equity", grid_values=(-1.0, 0.0, 1.0)),
                FactorAxis(factor_id="volatility", grid_values=(-1.0, 0.0, 1.0)),
            ),
        )
    )
    assert any(item.interaction_coefficient == -0.1 for item in result.interactions)
