from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    EvidenceClass,
    ReplayMode,
    S6State,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.m01_stress_scenario_taxonomy_and_commitment_registry import (
    build_scenario_registry,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.m02_historical_crisis_replay_and_regime_mapping_engine import (
    replay_historical_crisis,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    ExposureRecord,
    FactorMapping,
    HistoricalReplayRequest,
)


def test_uncommitted_scenario_is_invalid(context, scenario_request, factor_path):
    registry = build_scenario_registry(scenario_request)
    result = replay_historical_crisis(
        HistoricalReplayRequest(
            context=context,
            registry=registry,
            scenario_id="missing",
            factor_path=factor_path,
            exposures=(
                ExposureRecord(
                    exposure_id="e",
                    position_id="p",
                    current_factor_id="equity",
                    notional=1.0,
                    linear_sensitivity=1.0,
                    evidence_class=EvidenceClass.OBSERVED_HISTORICAL,
                ),
            ),
        )
    )
    assert result.status is S6State.INVALID


def test_proxy_mapping_and_dynamic_policy_are_explicit(context, scenario_request, factor_path):
    registry = build_scenario_registry(scenario_request)
    result = replay_historical_crisis(
        HistoricalReplayRequest(
            context=context,
            registry=registry,
            scenario_id="historical-crisis-1",
            factor_path=factor_path,
            exposures=(
                ExposureRecord(
                    exposure_id="e",
                    position_id="p",
                    current_factor_id="equity-proxy",
                    notional=1.0,
                    linear_sensitivity=1.0,
                    evidence_class=EvidenceClass.MODELLED,
                ),
            ),
            mappings=(
                FactorMapping(
                    current_factor_id="equity-proxy",
                    historical_factor_id="equity",
                    scale=0.8,
                    evidence_class=EvidenceClass.TRANSLATED_FACTOR,
                ),
            ),
            replay_mode=ReplayMode.FROZEN_DYNAMIC_POLICY,
            frozen_exposure_scales=(1.0, 0.8, 0.6, 0.4),
        )
    )
    assert result.status is S6State.SUCCESS_WITH_MAPPING_LIMITATIONS
    assert result.modelled_pnl_share > 0
