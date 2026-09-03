from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.m08_stress_model_and_scenario_validation_gate import (
    validate_stress_models,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import StressValidationRequest
from quant_pipeline.phase_09.subphases.s06_structural_stress.runner import run_s6


def test_validation_rejects_low_coverage_and_bad_mapping(full_request):
    bundle = run_s6(full_request)
    registry = bundle.scenario_registry.model_copy(update={"weighted_material_risk_coverage": 0.1})
    historical = bundle.historical_replay.model_copy(update={"mapped_exposure_share": 0.1})
    result = validate_stress_models(
        StressValidationRequest(
            context=bundle.context,
            registry=registry,
            historical_replay=historical,
            sensitivity=bundle.sensitivity,
            evt=bundle.evt,
            dro=bundle.dro,
            capacity=bundle.capacity,
            reverse_stress=bundle.reverse_stress,
        )
    )
    assert result.status is S6State.MODEL_NOT_FIT_FOR_STRESS
    assert "P9_STRESS_SCENARIO_COVERAGE_GAP" in result.reason_codes
