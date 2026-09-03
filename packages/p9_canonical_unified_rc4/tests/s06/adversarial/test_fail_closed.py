from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.m01_stress_scenario_taxonomy_and_commitment_registry import (
    build_scenario_registry,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.m03_factor_shock_and_global_sensitivity_surface_engine import (
    build_sensitivity_surface,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    FactorAxis,
    SensitivitySurfaceRequest,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import SensitivityPolicy


def test_surface_budget_fails_closed(context, scenario_request, response_model):
    registry = build_scenario_registry(scenario_request)
    result = build_sensitivity_surface(
        SensitivitySurfaceRequest(
            context=context,
            registry=registry,
            response_model=response_model,
            axes=(
                FactorAxis(factor_id="equity", grid_values=tuple(float(i) for i in range(-10, 11))),
                FactorAxis(factor_id="volatility", grid_values=tuple(float(i) for i in range(-10, 11))),
            ),
            policy=SensitivityPolicy(maximum_evaluations=100),
        )
    )
    assert result.status is S6State.INVALID
    assert "P9_STRESS_EVALUATION_BUDGET_EXCEEDED" in result.reason_codes
