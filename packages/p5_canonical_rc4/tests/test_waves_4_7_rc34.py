from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from quant_pipeline.phase_05_underlying_forecasts import ExecutionMode, PhaseRunner
from quant_pipeline.phase_05_underlying_forecasts.domain.v2_marginals import ReturnDistributionPanel
from quant_pipeline.phase_05_underlying_forecasts.domain.v2_publication import Phase6StrategyScenarioManifest
from quant_pipeline.phase_05_underlying_forecasts.domain.v2_scenarios import (
    AmbiguitySet,
    DependenceState,
    RegimeOODState,
    ScenarioPathPanel,
)
from quant_pipeline.phase_05_underlying_forecasts.errors import DataQualityError
from quant_pipeline.phase_05_underlying_forecasts.services.diagnostics import ood_score, page_hinkley
from quant_pipeline.phase_05_underlying_forecasts.services.regime import infer_regime
from quant_pipeline.phase_05_underlying_forecasts.services.scenario_engine import (
    joint_path_bundle,
    univariate_path_bundle,
    validate_scenario_bundle,
)

from .fixtures import build_fixture
from .test_full_pipeline import _context, offline_requests, publication_requests, runtime_requests


def _complete_pipeline(tmp_path: Path):
    fixture = build_fixture()
    offline = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run(offline_requests(fixture))
    runtime_context = _context(tmp_path, fixture, ExecutionMode.RUNTIME_INFERENCE)
    runtime = PhaseRunner(runtime_context).run(runtime_requests(), initial_artifacts=offline.artifacts)
    publication_context = _context(tmp_path, fixture, ExecutionMode.PUBLICATION)
    publication = PhaseRunner(publication_context).run(publication_requests(), initial_artifacts=runtime.artifacts)
    return fixture, runtime_context, publication_context, runtime, publication


def test_wave4_univariate_scenarios_are_qualified_and_stress_has_no_probability():
    generator = np.random.default_rng(11)
    values = generator.standard_t(df=6, size=180) * 0.01
    original = values.copy()
    bundle = univariate_path_bundle(values, seed=7, count=48, steps=5)
    assert {row["method"] for row in bundle["candidate_scores"]} == {"MOVING_BLOCK", "STATIONARY_BLOCK", "REGIME_BLOCK"}
    assert all(row["probability"] is None for row in bundle["stress_paths"])
    assert validate_scenario_bundle(bundle)["passed"] is True
    np.testing.assert_array_equal(values, original)


def test_wave4_joint_engine_compares_empirical_gaussian_and_t_copulas():
    generator = np.random.default_rng(13)
    residuals = generator.multivariate_normal(np.zeros(3), [[1.0, 0.6, 0.2], [0.6, 1.0, 0.5], [0.2, 0.5, 1.0]], size=160) * 0.01
    bundle = joint_path_bundle(residuals, np.array([0.001, 0.002, -0.001]), seed=9, count=48, steps=4)
    assert {row["method"] for row in bundle["candidate_scores"]} == {"EMPIRICAL_COPULA", "GAUSSIAN_COPULA", "T_COPULA"}
    assert bundle["champion_method"] in {"EMPIRICAL_COPULA", "GAUSSIAN_COPULA", "T_COPULA"}
    assert abs(sum(bundle["nominal_probabilities"]) - 1.0) < 1e-12


def test_wave5_regime_change_point_and_ood_are_evidence_based():
    generator = np.random.default_rng(17)
    values = np.concatenate([generator.normal(0.0, 0.5, 90), generator.normal(0.0, 2.0, 90)])
    regime = infer_regime(values)
    change = page_hinkley(values)
    reference = generator.normal(size=(100, 4))
    current = np.array([4.0, 0.0, 0.0, 0.0])
    ood = ood_score(reference, current)
    assert {row["method"] for row in regime["candidate_diagnostics"]} == {"ROLLING_VOLATILITY_MARKOV_COUNTS", "GAUSSIAN_HMM_EM"}
    assert abs(sum(regime["probabilities"].values()) - 1.0) < 1e-12
    assert 0.0 <= change["change_point_probability"] <= 1.0
    assert ood["threshold_calibration"] == "EMPIRICAL_REFERENCE_Q99"
    assert len(ood["feature_contributions"]) == 4


def test_wave6_publishes_strong_v2_contracts_and_manifest(tmp_path):
    _, _, publication_context, _, publication = _complete_pipeline(tmp_path)
    store = publication_context.artifact_store
    distributions = store.read(publication.artifacts["forecast_distribution_panel"])
    scenarios = store.read(publication.artifacts["forecast_scenario_panel"])
    ambiguity = store.read(publication.artifacts["ambiguity_set"])
    dependence = store.read(publication.artifacts["published_covariance_registry"])
    regime_ood = store.read(publication.artifacts["published_regime_ood_surprise_panel"])
    manifest_raw = store.read(publication.artifacts["phase6_strategy_scenario_manifest"])
    ReturnDistributionPanel.model_validate(distributions["return_distributions"]["artifact"])
    ScenarioPathPanel.model_validate(scenarios["artifact"])
    AmbiguitySet.model_validate(ambiguity["artifact"])
    DependenceState.model_validate(dependence["artifact"])
    RegimeOODState.model_validate(regime_ood["artifact"])
    manifest = Phase6StrategyScenarioManifest.model_validate(manifest_raw)
    references = [
        manifest.market_belief_state, manifest.return_distributions, manifest.volatility_distributions,
        manifest.path_risk_forecasts, manifest.scenario_paths, manifest.ambiguity_sets,
        manifest.dependence_states, manifest.regime_ood_states, manifest.forecast_confidence,
        manifest.availability_report, manifest.lineage_report,
    ]
    panel = ScenarioPathPanel.model_validate(scenarios["artifact"])
    stress = [row for row in panel.records if row.scenario_type.value == "STRESS"]
    assert stress and all(row.probability is None for row in stress)
    assert manifest.production_promotion_allowed is False
    assert manifest.scenario_capability == "LIMITED"
    assert manifest.extended_scenario_path_capability == "AVAILABLE"
    assert manifest.ambiguity_capability == "UNAVAILABLE"
    assert manifest.extended_ambiguity_capability == "AVAILABLE"
    assert manifest.producer_contract_version == "P5-P6-V2"
    assert manifest.handoff_mode == "DEGRADED_V2"
    assert manifest.published_artifacts[0] == "market_belief_state"
    assert len({ref.artifact_id for ref in references}) == 11


def test_wave7_generators_are_content_deterministic():
    values = np.linspace(-0.02, 0.02, 100)
    first = univariate_path_bundle(values, seed=33, count=24, steps=3)
    second = univariate_path_bundle(values, seed=33, count=24, steps=3)
    assert first == second


def test_wave7_scenario_validator_rejects_invalid_mass():
    bundle = univariate_path_bundle(np.linspace(-0.02, 0.02, 80), seed=3, count=24, steps=3)
    bundle["nominal_probabilities"][0] += 0.2
    report = validate_scenario_bundle(bundle)
    assert report["passed"] is False
    assert "INVALID_SCENARIO_MASS" in report["failures"]


def test_wave7_joint_engine_rejects_nonfinite_inputs():
    residuals = np.ones((40, 3), dtype=float)
    residuals[0, 0] = np.nan
    with pytest.raises(DataQualityError):
        joint_path_bundle(residuals, np.zeros(3), seed=1, count=24, steps=3)
