"""P9.S4 — institutional performance, risk, factor, execution, and capacity analytics."""

from .m01_returns import compute_returns
from .m02_distribution import compute_distribution
from .m03_tail_risk import compute_tail_risk
from .m04_drawdown import compute_drawdowns
from .m05_risk_adjusted import compute_risk_adjusted
from .m06_factor_regression import compute_factor_regressions
from .m07_execution_capacity import compute_execution_capacity
from .m08_quality_gate import reconcile_metrics
from .registries import default_factor_registry, default_metric_registry
from .service import S4AnalyticsRequest, S4AnalyticsResult, S4AnalyticsService

__all__ = [
    "S4AnalyticsRequest",
    "S4AnalyticsResult",
    "S4AnalyticsService",
    "compute_distribution",
    "compute_drawdowns",
    "compute_execution_capacity",
    "compute_factor_regressions",
    "compute_returns",
    "compute_risk_adjusted",
    "compute_tail_risk",
    "default_factor_registry",
    "default_metric_registry",
    "reconcile_metrics",
]
