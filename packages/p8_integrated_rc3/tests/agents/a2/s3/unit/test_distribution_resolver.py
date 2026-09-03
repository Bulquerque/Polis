from datetime import timedelta
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    BeliefRecord, DistributionType, MixtureComponent, MixturePayload, ParametricPayload,
    QuantilePayload,
)
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.errors import ContractIntegrityError
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.modules.distribution_resolver import resolve_distribution


def test_resolves_normal(normal_belief):
    result = resolve_distribution(normal_belief)
    assert result.path_capability == "TERMINAL_ONLY"
    assert result.factor_ids == ("A", "B")


def test_rejects_non_psd(normal_belief):
    bad = normal_belief.model_copy(update={"payload": ParametricPayload(family="NORMAL", mean=(0,0), covariance=((1,2),(2,1)))})
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(bad)


def test_mixture_weights_must_sum(normal_belief):
    payload = MixturePayload(components=(
        MixtureComponent(weight=0.4, family="NORMAL", mean=(0,0), covariance=((1,0),(0,1))),
        MixtureComponent(weight=0.4, family="NORMAL", mean=(1,1), covariance=((1,0),(0,1))),
    ))
    belief = normal_belief.model_copy(update={"distribution_type": DistributionType.MIXTURE, "payload": payload})
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(belief)


def test_quantiles_must_be_monotone(normal_belief):
    payload = QuantilePayload(levels=(0.1,0.5,0.9), values=((0,0),(1,1),(0.5,2)))
    belief = normal_belief.model_copy(update={"distribution_type": DistributionType.QUANTILE, "payload": payload})
    with pytest.raises(ContractIntegrityError):
        resolve_distribution(belief)


def test_quantile_without_dependence_warns(normal_belief):
    payload = QuantilePayload(levels=(0.1,0.5,0.9), values=((-1,-2),(0,0),(1,2)))
    belief = normal_belief.model_copy(update={"distribution_type": DistributionType.QUANTILE, "payload": payload})
    result = resolve_distribution(belief)
    assert "QUANTILE_DEPENDENCE_UNAVAILABLE_INDEPENDENT_COPULA" in result.warnings


def test_future_available_rejected(normal_belief):
    with pytest.raises(Exception):
        data = normal_belief.model_dump()
        data["available_at"] = normal_belief.decision_time + timedelta(seconds=1)
        BeliefRecord.model_validate(data)
