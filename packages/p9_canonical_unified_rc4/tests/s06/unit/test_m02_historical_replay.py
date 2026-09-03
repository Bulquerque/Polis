from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import EvidenceClass, S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.m01_stress_scenario_taxonomy_and_commitment_registry import (
    build_scenario_registry,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.m02_historical_crisis_replay_and_regime_mapping_engine import (
    replay_historical_crisis,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    ExposureRecord,
    HistoricalReplayRequest,
)


def test_historical_replay_preserves_recovery(context, scenario_request, factor_path):
    registry = build_scenario_registry(scenario_request)
    result = replay_historical_crisis(
        HistoricalReplayRequest(
            context=context,
            registry=registry,
            scenario_id="historical-crisis-1",
            factor_path=factor_path,
            exposures=(
                ExposureRecord(
                    exposure_id="e1",
                    position_id="p1",
                    current_factor_id="equity",
                    notional=100.0,
                    linear_sensitivity=1.0,
                    evidence_class=EvidenceClass.OBSERVED_HISTORICAL,
                ),
            ),
        )
    )
    assert result.status is S6State.SUCCESS
    assert result.recovery_included
    assert result.mapped_exposure_share == 1.0


def test_unmapped_material_exposure_fails_closed(context, scenario_request, factor_path):
    registry = build_scenario_registry(scenario_request)
    result = replay_historical_crisis(
        HistoricalReplayRequest(
            context=context,
            registry=registry,
            scenario_id="historical-crisis-1",
            factor_path=factor_path,
            exposures=(
                ExposureRecord(
                    exposure_id="e1",
                    position_id="p1",
                    current_factor_id="unknown-factor",
                    notional=100.0,
                    linear_sensitivity=1.0,
                    evidence_class=EvidenceClass.MODELLED,
                ),
            ),
        )
    )
    assert result.status is S6State.MATERIAL_EXPOSURE_UNMAPPED
    assert result.unmapped_notional == 100.0
