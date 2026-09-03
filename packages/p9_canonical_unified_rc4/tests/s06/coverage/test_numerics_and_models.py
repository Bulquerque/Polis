from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    BreachDirection,
    OutputSemantics,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    FactorAxis,
    FactorBound,
    FactorPath,
    QuadraticResponseModel,
    ScenarioProposal,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.numerics import (
    as_float_array,
    breach_margin,
    is_breached,
    linear_interpolate_zero,
    weighted_cvar,
)


def test_numerical_helpers_cover_edge_cases():
    assert weighted_cvar((1.0, 2.0), (0.5, 0.5), 0.5) == 2.0
    assert is_breached(1.0, 1.0, BreachDirection.GREATER_THAN_OR_EQUAL)
    assert breach_margin(2.0, 1.0, BreachDirection.GREATER_THAN_OR_EQUAL) == 1.0
    assert linear_interpolate_zero(0.0, 0.0, 1.0, 1.0) == 0.0
    assert linear_interpolate_zero(0.0, -1.0, 1.0, 0.0) == 1.0
    assert linear_interpolate_zero(0.0, 1.0, 1.0, 2.0) is None
    with pytest.raises(ValueError):
        as_float_array((float("nan"),))


def test_model_validators_reject_invalid_shapes(response_model):
    with pytest.raises(ValidationError):
        QuadraticResponseModel(
            model_id="bad",
            factor_ids=("a", "b"),
            units=("u", "u"),
            baseline_value=0.0,
            linear_coefficients=(1.0, 1.0),
            quadratic_matrix=((0.0, 1.0), (0.0, 0.0)),
            semantics=OutputSemantics.PNL,
            model_sha256=content_sha256({"bad": True}),
        )
    with pytest.raises(ValidationError):
        FactorAxis(factor_id="x", grid_values=(0.0, 0.0))
    with pytest.raises(ValidationError):
        FactorBound(factor_id="x", lower=0.1, upper=1.0)


def test_factor_path_and_scenario_validators():
    with pytest.raises(ValidationError):
        FactorPath(
            path_id="bad",
            timestamps=(datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)),
            factor_ids=("x",),
            values=((0.0,), (1.0,)),
            units=("u",),
            evidence_classes=("OBSERVED_HISTORICAL",),
        )
    with pytest.raises(ValidationError):
        ScenarioProposal(
            scenario_id="bad",
            name="bad",
            scenario_class="HISTORICAL_REPLAY",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            purpose="test",
            approved_uses=("RESEARCH",),
            prohibited_uses=("RESEARCH",),
            shocks=(),
            horizon_days=1,
            severity_label="S",
            plausibility_label="P",
        )
