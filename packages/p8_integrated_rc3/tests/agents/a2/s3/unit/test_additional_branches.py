from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import hashlib
import sys

import numpy as np
import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.arrays import ScenarioSet, StressScenarioSet
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.cli import main as cli_main
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.compat.rc4_1 import adapt_rc4_1_belief
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ActionabilityPolicy,
    ArtifactRef,
    BeliefRecord,
    DistributionType,
    EmpiricalPayload,
    HorizonSpec,
    HorizonUnit,
    MixtureComponent,
    MixturePayload,
    ParametricPayload,
    PathPayload,
    ProbabilityMeasure,
    QualityAssessment,
    QualityStatus,
    QuantilePayload,
    ReductionAssessment,
    ReductionStatus,
    ScenarioPolicy,
    StressPolicy,
    StressTemplate,
)
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.errors import (
    ContractIntegrityError,
    NumericalIntegrityError,
    ProbabilityIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.hashing import canonical_sha256
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.ambiguity_compiler import compile_ambiguity
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.distribution_resolver import resolve_distribution
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_materializer import materialize_scenarios
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.stress_factory import build_stresses, find_reverse_stress
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.ports import RiskResponse
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.random_stream import RandomStream


def _belief(normal_belief, distribution_type, payload):
    return normal_belief.model_copy(update={"distribution_type": distribution_type, "payload": payload})


def _quality(score, status):
    return QualityAssessment(status_by_family={"LINEAR": status}, score=score, metrics=())


def _reduction():
    return ReductionAssessment(
        status=ReductionStatus.SAFE, original_count=32, output_count=8,
        mean_error=0, covariance_error=0, tail_error=0, transport_cost=0,
        decision_aware_status="CAPABILITY_UNAVAILABLE", content_sha256="a"*64,
    )


class NeverFails:
    def evaluate(self, shock_vector):
        return RiskResponse(loss=0.0, margin=0.0, liquidity=1.0, failure_states=())


def test_student_t_requires_dof(normal_belief):
    payload = ParametricPayload(family="STUDENT_T", mean=(0, 0), covariance=((1, 0), (0, 1)))
    belief = _belief(normal_belief, DistributionType.PARAMETRIC, payload)
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(belief)


def test_student_t_materializes_heavy_tails(normal_belief):
    payload = ParametricPayload(
        family="STUDENT_T", mean=(0, 0), covariance=((1, 0), (0, 1)), degrees_freedom=3.5,
    )
    belief = _belief(normal_belief, DistributionType.PARAMETRIC, payload)
    scenarios = materialize_scenarios(belief, ScenarioPolicy(scenario_count=2048, seed_entropy=31))
    assert np.quantile(np.abs(scenarios.values[:, 0, 0]), 0.99) > 2.5


def test_student_t_mixture_component_requires_dof(normal_belief):
    payload = MixturePayload(components=(
        MixtureComponent(weight=0.5, family="STUDENT_T", mean=(0, 0), covariance=((1, 0), (0, 1))),
        MixtureComponent(weight=0.5, family="NORMAL", mean=(1, 1), covariance=((1, 0), (0, 1))),
    ))
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(_belief(normal_belief, DistributionType.MIXTURE, payload))


def test_empirical_shape_and_probability_validation(normal_belief):
    wrong_shape = EmpiricalPayload(samples=((1.0,), (2.0,)))
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(_belief(normal_belief, DistributionType.EMPIRICAL, wrong_shape))
    wrong_probability = EmpiricalPayload(samples=((1.0, 2.0), (2.0, 3.0)), probabilities=(0.2, 0.2))
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(_belief(normal_belief, DistributionType.EMPIRICAL, wrong_probability))


def test_path_payload_resolution_and_materialization(normal_belief):
    payload = PathPayload(
        paths=(((0.1, 0.2), (0.2, 0.3)), ((-0.1, 0.0), (-0.2, 0.1))),
        probabilities=(0.6, 0.4), step_labels=("T1", "T2"),
    )
    belief = _belief(normal_belief, DistributionType.PATH, payload)
    resolution = resolve_distribution(belief)
    scenarios = materialize_scenarios(belief, ScenarioPolicy(scenario_count=32, seed_entropy=5))
    assert resolution.path_capability == "FULL_PATH"
    assert scenarios.shape == (32, 2, 2)
    assert scenarios.step_labels == ("T1", "T2")


def test_path_step_label_mismatch(normal_belief):
    payload = PathPayload(
        paths=(((0.1, 0.2), (0.2, 0.3)),), step_labels=("ONLY_ONE",),
    )
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(_belief(normal_belief, DistributionType.PATH, payload))


def test_quantile_level_and_correlation_validation(normal_belief):
    invalid_levels = QuantilePayload(levels=(0.5, 0.4), values=((0, 0), (1, 1)))
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(_belief(normal_belief, DistributionType.QUANTILE, invalid_levels))
    invalid_correlation = QuantilePayload(
        levels=(0.1, 0.9), values=((-1, -1), (1, 1)),
        gaussian_copula_correlation=((1, 2), (2, 1)),
    )
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(_belief(normal_belief, DistributionType.QUANTILE, invalid_correlation))


def test_contract_distribution_payload_mismatch(normal_belief):
    data = normal_belief.model_dump()
    data["distribution_type"] = "EMPIRICAL"
    with pytest.raises(ValidationError):
        BeliefRecord.model_validate(data)


def test_scenario_set_metadata_and_nonfinite_rejected():
    with pytest.raises(NumericalIntegrityError):
        ScenarioSet(
            values=np.zeros((2, 1, 1)), probabilities=np.array([0.5, 0.5]),
            scenario_ids=("one",), factor_ids=("A",), step_labels=("T",), origins=("x", "x"),
        )
    with pytest.raises(NumericalIntegrityError):
        ScenarioSet(
            values=np.array([[[np.nan]]]), probabilities=np.array([1.0]),
            scenario_ids=("one",), factor_ids=("A",), step_labels=("T",), origins=("x",),
        )
    with pytest.raises(ProbabilityIntegrityError):
        ScenarioSet(
            values=np.zeros((2, 1, 1)), probabilities=np.array([1.1, -0.1]),
            scenario_ids=("one", "two"), factor_ids=("A",), step_labels=("T",), origins=("x", "x"),
        )


def test_stress_set_metadata_rejected():
    with pytest.raises(NumericalIntegrityError):
        StressScenarioSet(
            values=np.zeros((2, 1, 1)), stress_ids=("one",), factor_ids=("A",),
            step_labels=("T",), severities=(1, 1), tags=((), ()),
        )


def test_multiplicative_and_default_stress(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    baseline = np.average(scenarios.values, axis=0, weights=scenarios.probabilities)
    default = build_stresses(scenarios, StressPolicy())
    assert default.stress_ids == ("BASELINE_NO_EXPLICIT_STRESS",)
    policy = StressPolicy(templates=(StressTemplate(
        stress_id="multiply", factor_shocks={"A": 0.5}, mode="MULTIPLICATIVE",
    ),))
    multiplied = build_stresses(scenarios, policy)
    assert multiplied.values[0, 0, 0] == pytest.approx(baseline[0, 0] * 1.5)


def test_reverse_stress_no_failure_within_bound():
    status, multiplier, states = find_reverse_stress((-1.0,), NeverFails(), StressPolicy(reverse_stress_max_multiplier=2))
    assert status == "NO_FAILURE_WITHIN_BOUND"
    assert multiplier is None and states == ()


def test_random_stream_namespace_and_sobol():
    first = RandomStream(123, "A").generator().integers(0, 100, 5)
    second = RandomStream(123, "A").generator().integers(0, 100, 5)
    different = RandomStream(123, "B").generator().integers(0, 100, 5)
    np.testing.assert_array_equal(first, second)
    assert not np.array_equal(first, different)
    sobol = RandomStream(123, "S").sobol_uniforms(3, 10)
    assert sobol.shape == (10, 3)
    assert np.all((sobol >= 0) & (sobol <= 1))


def test_hash_supports_path_enum_and_rejects_nonfinite(tmp_path):
    digest = canonical_sha256({"path": tmp_path, "measure": ProbabilityMeasure.PHYSICAL})
    assert len(digest) == 64
    with pytest.raises(ValueError):
        canonical_sha256({"x": float("inf")})


def test_actionability_robust_degraded_and_no_new_risk(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    policy = ActionabilityPolicy()
    robust = compile_ambiguity(
        scenarios, _quality(0.9, QualityStatus.FULLY_QUALIFIED), _reduction(),
        0.9, 0.25, 0.1, None, policy,
    )
    degraded = compile_ambiguity(
        scenarios, _quality(0.7, QualityStatus.QUALIFIED_WITH_HAIRCUT), _reduction(),
        0.7, 0.35, 0.3, None, policy,
    )
    no_new = compile_ambiguity(
        scenarios, _quality(0.4, QualityStatus.REGIME_INCOMPLETE), _reduction(),
        0.5, 0.6, 0.5, None, policy,
    )
    assert robust.actionability_state.value in {"ROBUST_ONLY", "DEGRADED_ACTIONABLE"}
    assert degraded.actionability_state.value in {"DEGRADED_ACTIONABLE", "NO_NEW_RISK"}
    assert no_new.actionability_state.value in {"NO_NEW_RISK", "NO_ACTION_VALID"}


def test_missing_uncertainty_evidence_records_reasons(normal_belief):
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=32))
    result = compile_ambiguity(
        scenarios, _quality(0.9, QualityStatus.FULLY_QUALIFIED), _reduction(),
        0.9, None, None, None, ActionabilityPolicy(),
    )
    assert "OOD_EVIDENCE_UNAVAILABLE" in result.reason_codes
    assert "DISAGREEMENT_EVIDENCE_UNAVAILABLE" in result.reason_codes


def test_rc4_adapter_missing_fields(now):
    payload = ParametricPayload(family="NORMAL", mean=(0.1,), covariance=((0.04,),))
    with pytest.raises(ContractIntegrityError):
        adapt_rc4_1_belief({}, payload, hashlib.sha256(b"x").hexdigest())


def test_cli_main_direct(monkeypatch, s3_request, tmp_path, capsys):
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "out"
    request_path.write_text(s3_request.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["p8-s3-run", str(request_path), str(output_path)])
    cli_main()
    assert '"run_id": "run-1"' in capsys.readouterr().out
    assert (output_path / "s3_result.json").exists()


def test_naive_datetime_rejected(normal_belief):
    data = normal_belief.model_dump()
    data["decision_time"] = normal_belief.decision_time.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        BeliefRecord.model_validate(data)


def test_reduction_pairwise_guard_returns_full(normal_belief):
    from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import ReductionPolicy
    from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.scenario_reduction import reduce_scenarios
    scenarios = materialize_scenarios(normal_belief, ScenarioPolicy(scenario_count=128))
    reduced, assessment = reduce_scenarios(
        scenarios,
        ReductionPolicy(target_count=16, max_pairwise_elements=10_000),
    )
    assert assessment.status == ReductionStatus.CAPABILITY_UNAVAILABLE
    assert reduced is scenarios
