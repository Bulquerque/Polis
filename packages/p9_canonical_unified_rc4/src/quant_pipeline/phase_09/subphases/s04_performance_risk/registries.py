"""Canonical metric and factor registries for P9.S4 RC1."""

from __future__ import annotations

from .bundle_models import MetricRegistry, MetricRegistryEntry
from .common import GrossNet, Unit, content_sha256
from .factor_models import FactorModelRegistry, FactorModelSpec


def default_factor_registry() -> FactorModelRegistry:
    return FactorModelRegistry(
        registry_id="P9_S4_FACTOR_MODELS",
        registry_version="1.0.0",
        models=(
            FactorModelSpec(
                factor_model_id="CAPM",
                factor_model_version="1.0.0",
                factor_ids=("MKT_RF",),
                description="Market excess return factor model",
            ),
            FactorModelSpec(
                factor_model_id="FF3",
                factor_model_version="1.0.0",
                factor_ids=("MKT_RF", "SMB", "HML"),
                description="Fama-French three-factor model",
            ),
            FactorModelSpec(
                factor_model_id="FF5",
                factor_model_version="1.0.0",
                factor_ids=("MKT_RF", "SMB", "HML", "RMW", "CMA"),
                description="Fama-French five-factor model",
            ),
            FactorModelSpec(
                factor_model_id="FF5_MOM",
                factor_model_version="1.0.0",
                factor_ids=("MKT_RF", "SMB", "HML", "RMW", "CMA", "MOM"),
                description="Fama-French five factors plus momentum",
            ),
        ),
    )


def default_metric_registry() -> MetricRegistry:
    rows = [
        ("return.cumulative", Unit.DECIMAL_RETURN, (GrossNet.GROSS, GrossNet.NET)),
        ("return.cagr", Unit.ANNUALIZED_DECIMAL, (GrossNet.GROSS, GrossNet.NET)),
        ("return.arithmetic_mean", Unit.DECIMAL_RETURN, (GrossNet.GROSS, GrossNet.NET)),
        ("return.geometric_mean", Unit.DECIMAL_RETURN, (GrossNet.GROSS, GrossNet.NET)),
        ("risk.volatility", Unit.ANNUALIZED_DECIMAL, (GrossNet.GROSS, GrossNet.NET)),
        ("risk.downside_deviation", Unit.ANNUALIZED_DECIMAL, (GrossNet.GROSS, GrossNet.NET)),
        ("risk.upside_deviation", Unit.ANNUALIZED_DECIMAL, (GrossNet.GROSS, GrossNet.NET)),
        ("distribution.skewness", Unit.COEFFICIENT, (GrossNet.GROSS, GrossNet.NET)),
        ("distribution.excess_kurtosis", Unit.COEFFICIENT, (GrossNet.GROSS, GrossNet.NET)),
        ("tail.var.*", Unit.DECIMAL_RETURN, (GrossNet.GROSS, GrossNet.NET)),
        ("tail.expected_shortfall.*", Unit.DECIMAL_RETURN, (GrossNet.GROSS, GrossNet.NET)),
        ("tail.var_normal.*", Unit.DECIMAL_RETURN, (GrossNet.GROSS, GrossNet.NET)),
        ("tail.expected_shortfall_normal.*", Unit.DECIMAL_RETURN, (GrossNet.GROSS, GrossNet.NET)),
        ("tail.ratio.*", Unit.RATIO, (GrossNet.GROSS, GrossNet.NET)),
        ("drawdown.maximum", Unit.FRACTION, (GrossNet.NET,)),
        ("drawdown.average", Unit.FRACTION, (GrossNet.NET,)),
        ("drawdown.conditional_expected", Unit.FRACTION, (GrossNet.NET,)),
        ("drawdown.maximum_duration", Unit.SECONDS, (GrossNet.NET,)),
        ("drawdown.maximum_recovery", Unit.SECONDS, (GrossNet.NET,)),
        ("drawdown.time_underwater", Unit.FRACTION, (GrossNet.NET,)),
        ("ratio.sharpe", Unit.RATIO, (GrossNet.NET,)),
        ("ratio.sharpe_autocorrelation_adjusted", Unit.RATIO, (GrossNet.NET,)),
        ("ratio.psr", Unit.PROBABILITY, (GrossNet.NET,)),
        ("ratio.sortino", Unit.RATIO, (GrossNet.NET,)),
        ("ratio.omega", Unit.RATIO, (GrossNet.NET,)),
        ("ratio.calmar", Unit.RATIO, (GrossNet.NET,)),
        ("risk.tracking_error", Unit.ANNUALIZED_DECIMAL, (GrossNet.ACTIVE,)),
        ("ratio.information", Unit.RATIO, (GrossNet.ACTIVE,)),
        ("factor.*.alpha_annualized", Unit.ANNUALIZED_DECIMAL, (GrossNet.GROSS, GrossNet.NET)),
        ("factor.*.r_squared", Unit.RATIO, (GrossNet.GROSS, GrossNet.NET)),
        ("factor.*.residual_volatility", Unit.ANNUALIZED_DECIMAL, (GrossNet.GROSS, GrossNet.NET)),
        ("factor.*.*", Unit.COEFFICIENT, (GrossNet.GROSS, GrossNet.NET)),
        ("execution.fill_rate", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.partial_fill_rate", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.rejection_rate", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.turnover", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.average_leverage", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.peak_leverage", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.average_margin_utilization", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.peak_margin_utilization", Unit.RATIO, (GrossNet.NOT_APPLICABLE,)),
        ("execution.slippage_fraction", Unit.FRACTION, (GrossNet.NOT_APPLICABLE,)),
    ]
    entries = tuple(
        MetricRegistryEntry(
            metric_pattern=pattern,
            metric_version="1.0.0",
            producer_module_id="P9.S4",
            unit=unit.value,
            allowed_gross_net=tuple(item.value for item in gross_net),
        )
        for pattern, unit, gross_net in rows
    )
    body = {
        "registry_id": "P9_S4_METRICS",
        "registry_version": "1.0.0",
        "entries": entries,
    }
    return MetricRegistry(**body, content_sha256=content_sha256(body))
