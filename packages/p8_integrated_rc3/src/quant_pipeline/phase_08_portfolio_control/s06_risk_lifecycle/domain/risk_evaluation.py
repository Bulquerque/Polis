from __future__ import annotations

from collections import defaultdict

from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import (
    DecisionReadyRiskBundle,
)

from ..contracts.canonicalization import canonical_sha256
from ..models.artifacts import ExposureLimitResult, HorizonRiskMetrics, IndependentRiskGateReport
from ..models.enums import RiskGateStatus
from ..models.policies import RiskGatePolicy
from .risk_math import weighted_cvar

ScenarioMap = tuple[float, dict[str, tuple[float, ...]]]
StressMap = tuple[float, dict[str, tuple[float, ...]]]


def _coefficient(candidate, attribute: str, quantity: float) -> float:
    value = getattr(candidate, attribute)
    if value is not None:
        return float(value)
    if abs(quantity) <= 1e-12:
        return 0.0
    raise ValueError(
        f"{attribute} unavailable for non-zero candidate quantity {candidate.candidate_id}"
    )


def _scenario_maps(bundle: DecisionReadyRiskBundle) -> list[ScenarioMap]:
    return [
        (
            scenario.probability,
            {row.candidate_id: row.incremental_pnl_by_horizon for row in scenario.candidate_pnl},
        )
        for scenario in bundle.payload.scenarios
    ]


def _stress_maps(bundle: DecisionReadyRiskBundle) -> list[StressMap]:
    return [
        (
            stress.portfolio_loss_limit,
            {row.candidate_id: row.incremental_pnl_by_horizon for row in stress.candidate_pnl},
        )
        for stress in bundle.payload.mandatory_stresses
    ]


def _resource_metrics(
    bundle: DecisionReadyRiskBundle,
    quantities: dict[str, tuple[float, ...]],
    horizon_index: int,
) -> tuple[float, float, float]:
    candidate_map = {candidate.candidate_id: candidate for candidate in bundle.payload.candidates}
    capital = margin = maximum_loss = 0.0
    for candidate_id, path in quantities.items():
        magnitude = abs(path[horizon_index])
        candidate = candidate_map[candidate_id]
        capital += magnitude * _coefficient(candidate, "capital_per_unit", magnitude)
        margin += magnitude * _coefficient(candidate, "margin_per_unit", magnitude)
        maximum_loss += magnitude * _coefficient(candidate, "maximum_loss_per_unit", magnitude)
    return capital, margin, maximum_loss


def _scenario_losses(
    scenarios: list[ScenarioMap],
    quantities: dict[str, tuple[float, ...]],
    horizon_index: int,
) -> tuple[list[float], list[float]]:
    losses = [
        -sum(path[horizon_index] * quantities[candidate_id][horizon_index] for candidate_id, path in rows.items())
        for _, rows in scenarios
    ]
    probabilities = [probability for probability, _ in scenarios]
    return losses, probabilities


def _stress_losses(
    stresses: list[StressMap],
    quantities: dict[str, tuple[float, ...]],
    horizon_index: int,
) -> list[float]:
    return [
        max(
            0.0,
            -sum(
                path[horizon_index] * quantities[candidate_id][horizon_index]
                for candidate_id, path in rows.items()
            ),
        )
        for _, rows in stresses
    ]


def _horizon_metrics(
    bundle: DecisionReadyRiskBundle,
    quantities: dict[str, tuple[float, ...]],
    scenarios: list[ScenarioMap],
    stresses: list[StressMap],
    horizon_index: int,
    tolerance: float,
) -> HorizonRiskMetrics:
    limits = bundle.payload.risk_limits
    capital, margin, maximum_loss = _resource_metrics(bundle, quantities, horizon_index)
    losses, probabilities = _scenario_losses(scenarios, quantities, horizon_index)
    cvar = weighted_cvar(losses, probabilities, limits.cvar_alpha) if scenarios else None
    stress_losses = _stress_losses(stresses, quantities, horizon_index)
    stress_ok = all(
        loss <= stress_limit + tolerance
        for loss, (stress_limit, _) in zip(stress_losses, stresses, strict=True)
    )
    checks = (
        (capital <= limits.maximum_capital_by_horizon[horizon_index] + tolerance, "CAPITAL_LIMIT_BREACH"),
        (margin <= limits.maximum_margin_by_horizon[horizon_index] + tolerance, "MARGIN_LIMIT_BREACH"),
        (maximum_loss <= limits.maximum_loss_by_horizon[horizon_index] + tolerance, "MAXIMUM_LOSS_LIMIT_BREACH"),
        (
            cvar is None or limits.maximum_cvar is None or cvar <= limits.maximum_cvar + tolerance,
            "CVAR_LIMIT_BREACH",
        ),
        (stress_ok, "MANDATORY_STRESS_LIMIT_BREACH"),
    )
    reasons = tuple(reason for passed, reason in checks if not passed)
    horizon = bundle.payload.horizons[horizon_index]
    return HorizonRiskMetrics(
        horizon_id=horizon.horizon_id,
        capital=capital,
        margin=margin,
        maximum_loss=maximum_loss,
        cvar=cvar,
        maximum_stress_loss=max(stress_losses, default=None),
        capital_limit=limits.maximum_capital_by_horizon[horizon_index],
        margin_limit=limits.maximum_margin_by_horizon[horizon_index],
        maximum_loss_limit=limits.maximum_loss_by_horizon[horizon_index],
        cvar_limit=limits.maximum_cvar,
        feasible=not reasons,
        reason_codes=reasons,
    )


def _aggregate_exposures(
    bundle: DecisionReadyRiskBundle,
    quantities: dict[str, tuple[float, ...]],
    horizon_index: int,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    candidate_map = {candidate.candidate_id: candidate for candidate in bundle.payload.candidates}
    greek_values: dict[str, float] = defaultdict(float)
    underlying_values: dict[str, float] = defaultdict(float)
    expiration_values: dict[str, float] = defaultdict(float)
    for candidate_id, path in quantities.items():
        candidate = candidate_map[candidate_id]
        quantity = path[horizon_index]
        capital = abs(quantity) * _coefficient(candidate, "capital_per_unit", quantity)
        underlying_values[candidate.underlying_bucket] += capital
        expiration_values[candidate.expiration_bucket] += capital
        for greek in candidate.greeks:
            greek_values[greek.greek_name] += quantity * greek.value_per_unit
    return greek_values, underlying_values, expiration_values


def _greek_results(
    bundle: DecisionReadyRiskBundle,
    values: dict[str, float],
    horizon_index: int,
    tolerance: float,
) -> list[ExposureLimitResult]:
    horizon_id = bundle.payload.horizons[horizon_index].horizon_id
    available_greeks = {
        greek.greek_name
        for candidate in bundle.payload.candidates
        for greek in candidate.greeks
    }
    results = []
    for limit in bundle.payload.risk_limits.greek_limits:
        available = limit.greek_name in available_greeks
        value = values.get(limit.greek_name, 0.0)
        minimum = limit.minimum_by_horizon[horizon_index]
        maximum = limit.maximum_by_horizon[horizon_index]
        results.append(
            ExposureLimitResult(
                exposure_type="GREEK",
                bucket_id=limit.greek_name,
                horizon_id=horizon_id,
                value=value,
                minimum=minimum,
                maximum=maximum,
                available=available,
                feasible=available and minimum - tolerance <= value <= maximum + tolerance,
                reason_codes=() if available else ("REQUIRED_GREEK_UNAVAILABLE",),
            )
        )
    return results


def _concentration_results(
    bundle: DecisionReadyRiskBundle,
    values: dict[str, float],
    horizon_index: int,
    tolerance: float,
    exposure_type: str,
) -> list[ExposureLimitResult]:
    horizon_id = bundle.payload.horizons[horizon_index].horizon_id
    limits = (
        bundle.payload.risk_limits.underlying_concentration
        if exposure_type == "UNDERLYING_CONCENTRATION"
        else bundle.payload.risk_limits.expiration_concentration
    )
    return [
        ExposureLimitResult(
            exposure_type=exposure_type,
            bucket_id=limit.bucket_id,
            horizon_id=horizon_id,
            value=values.get(limit.bucket_id, 0.0),
            maximum=limit.maximum_capital_by_horizon[horizon_index],
            feasible=values.get(limit.bucket_id, 0.0)
            <= limit.maximum_capital_by_horizon[horizon_index] + tolerance,
        )
        for limit in limits
    ]


def _exposure_results(
    bundle: DecisionReadyRiskBundle,
    quantities: dict[str, tuple[float, ...]],
    tolerance: float,
) -> list[ExposureLimitResult]:
    results: list[ExposureLimitResult] = []
    for horizon_index, _ in enumerate(bundle.payload.horizons):
        greeks, underlyings, expirations = _aggregate_exposures(bundle, quantities, horizon_index)
        results.extend(_greek_results(bundle, greeks, horizon_index, tolerance))
        results.extend(
            _concentration_results(
                bundle, underlyings, horizon_index, tolerance, "UNDERLYING_CONCENTRATION"
            )
        )
        results.extend(
            _concentration_results(
                bundle, expirations, horizon_index, tolerance, "EXPIRATION_CONCENTRATION"
            )
        )
    return results


def _relevant_horizons(
    metrics: list[HorizonRiskMetrics],
    policy: RiskGatePolicy,
) -> tuple[set[str], bool]:
    block_all = policy.require_all_horizons or policy.block_on_future_plan_violation
    relevant = {metric.horizon_id for metric in metrics} if block_all else {metrics[0].horizon_id}
    return relevant, block_all


def _blocking_reasons(
    metrics: list[HorizonRiskMetrics],
    exposures: list[ExposureLimitResult],
    relevant: set[str],
) -> set[str]:
    reasons = {
        reason
        for metric in metrics
        if metric.horizon_id in relevant
        for reason in metric.reason_codes
    }
    blocked_exposures = [
        result
        for result in exposures
        if result.horizon_id in relevant and not result.feasible
    ]
    if blocked_exposures:
        reasons.add("EXPOSURE_LIMIT_BREACH")
        reasons.update(
            reason
            for result in blocked_exposures
            for reason in result.reason_codes
        )
    return reasons


def _has_future_violation(
    metrics: list[HorizonRiskMetrics],
    exposures: list[ExposureLimitResult],
    relevant: set[str],
) -> bool:
    metric_violation = any(not metric.feasible for metric in metrics[1:])
    exposure_violation = any(
        not result.feasible and result.horizon_id not in relevant
        for result in exposures
    )
    return metric_violation or exposure_violation


def _blocking_result(
    metrics: list[HorizonRiskMetrics],
    exposures: list[ExposureLimitResult],
    policy: RiskGatePolicy,
) -> tuple[bool, tuple[str, ...]]:
    relevant, block_all = _relevant_horizons(metrics, policy)
    relevant_metrics_ok = all(
        metric.feasible for metric in metrics if metric.horizon_id in relevant
    )
    relevant_exposures_ok = all(
        result.feasible for result in exposures if result.horizon_id in relevant
    )
    reasons = _blocking_reasons(metrics, exposures, relevant)
    if _has_future_violation(metrics, exposures, relevant) and not block_all:
        reasons.add("FUTURE_PLAN_ADVISORY_VIOLATION")
    return relevant_metrics_ok and relevant_exposures_ok, tuple(sorted(reasons))


def evaluate_target(
    bundle: DecisionReadyRiskBundle,
    quantities: dict[str, tuple[float, ...]],
    policy: RiskGatePolicy,
    target_hash: str,
    optimizer_claimed_feasible: bool,
) -> IndependentRiskGateReport:
    scenarios = _scenario_maps(bundle)
    stresses = _stress_maps(bundle)
    metrics = [
        _horizon_metrics(
            bundle, quantities, scenarios, stresses, index, policy.numerical_tolerance
        )
        for index, _ in enumerate(bundle.payload.horizons)
    ]
    exposures = _exposure_results(bundle, quantities, policy.numerical_tolerance)
    feasible, reason_codes = _blocking_result(metrics, exposures, policy)
    discrepancy = 0.0 if optimizer_claimed_feasible == feasible else 1.0
    status = RiskGateStatus.APPROVED if feasible else RiskGateStatus.RISK_BLOCKED
    if not quantities:
        status = RiskGateStatus.NO_ACTION_VALID
    draft = IndependentRiskGateReport(
        status=status,
        horizon_metrics=tuple(metrics),
        exposure_limits=tuple(exposures),
        optimizer_claimed_feasible=optimizer_claimed_feasible,
        independently_feasible=feasible,
        maximum_optimizer_risk_discrepancy=discrepancy,
        decision_snapshot_hash=bundle.payload.decision_snapshot_hash,
        target_hash=target_hash,
        report_hash="0" * 64,
        reason_codes=reason_codes,
    )
    unsigned = draft.model_copy(update={"report_hash": "0" * 64})
    return draft.model_copy(update={"report_hash": canonical_sha256(unsigned)})
