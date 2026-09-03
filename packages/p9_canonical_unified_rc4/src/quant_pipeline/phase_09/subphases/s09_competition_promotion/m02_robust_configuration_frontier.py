from __future__ import annotations

from quant_pipeline.phase_09.errors import ContractError

from collections import defaultdict, deque
from statistics import fmean, pstdev

from .enums import (
    FrontierState,
    GateState,
    ModuleStatus,
    OptimizationDirection,
    ParameterRegionState,
)
from .hashing import sha256_hex
from .models.common import ModuleDiagnostics, ModuleResult, build_module_result
from .models.frontier import (
    CohortFrontier,
    ConfigurationEvaluationCard,
    DominatedConfiguration,
    FrontierBuildPolicy,
    ParameterDimension,
    ParameterRegion,
    ParameterScalar,
    ParameterSpaceRegistry,
    RobustConfigurationFrontier,
)
from .models.policy import CompetitionObjectivePolicy, FrontierAxis
from .scoring import configuration_utility, oriented

MODULE_ID = "P9.S9.M02"


def _passes_hard_gates(
    card: ConfigurationEvaluationCard,
    policy: CompetitionObjectivePolicy,
) -> tuple[bool, tuple[str, ...]]:
    gates = card.gate_map()
    reasons: list[str] = []
    for rule in policy.hard_gates:
        state = gates.get(rule.gate_id)
        if state is None:
            if rule.missing_is_failure:
                reasons.append(f"missing gate {rule.gate_id}")
            continue
        if state.value not in rule.accepted_states:
            reasons.append(f"gate {rule.gate_id}={state.value}")
    if card.dsr < policy.minimum_dsr:
        reasons.append("DSR below policy minimum")
    if card.pbo > policy.maximum_pbo:
        reasons.append("PBO above policy maximum")
    if not card.capacity_feasible:
        reasons.append("capacity infeasible")
    if not card.stress_resilient:
        reasons.append("stress resilience failed")
    if card.live_degradation_detected:
        reasons.append("live degradation detected")
    return not reasons, tuple(reasons)


def _axis_value(card: ConfigurationEvaluationCard, axis: FrontierAxis) -> float:
    metrics = card.metric_map()
    if axis.metric_id not in metrics:
        raise KeyError(f"configuration {card.configuration_id} lacks axis {axis.metric_id}")
    return oriented(metrics[axis.metric_id], axis.direction)


def _dominates(
    left: ConfigurationEvaluationCard,
    right: ConfigurationEvaluationCard,
    axes: tuple[FrontierAxis, ...],
) -> bool:
    no_worse = True
    strictly_better = False
    for axis in axes:
        left_value = _axis_value(left, axis)
        right_value = _axis_value(right, axis)
        if left_value < right_value - axis.epsilon:
            no_worse = False
            break
        if left_value > right_value + axis.epsilon:
            strictly_better = True
    return no_worse and strictly_better


def _numeric_distance(
    value: ParameterScalar,
    other: ParameterScalar,
    dimension: ParameterDimension,
) -> float:
    if isinstance(value, bool) or isinstance(other, bool):
        raise TypeError(f"numeric parameter {dimension.name} cannot be boolean")
    if not isinstance(value, (int, float)) or not isinstance(other, (int, float)):
        raise TypeError(f"numeric parameter {dimension.name} requires numeric values")
    if dimension.numeric_minimum is None or dimension.numeric_maximum is None:
        raise ContractError(f"numeric parameter {dimension.name} lacks bounds")
    scale = dimension.numeric_maximum - dimension.numeric_minimum
    return abs(float(value) - float(other)) / scale


def _categorical_distance(
    value: ParameterScalar,
    other: ParameterScalar,
    dimension: ParameterDimension,
) -> float:
    if not isinstance(value, str) or not isinstance(other, str):
        raise TypeError(f"categorical parameter {dimension.name} requires strings")
    if value not in dimension.allowed_categories or other not in dimension.allowed_categories:
        raise ValueError(f"categorical value outside registry for {dimension.name}")
    return 0.0 if value == other else 1.0


def _parameter_distance(
    left: ConfigurationEvaluationCard,
    right: ConfigurationEvaluationCard,
    registry: ParameterSpaceRegistry,
) -> float:
    left_values = left.parameter_map()
    right_values = right.parameter_map()
    distances: list[float] = []
    for dimension in registry.dimensions:
        if dimension.name not in left_values or dimension.name not in right_values:
            raise KeyError(f"missing registered parameter {dimension.name}")
        if dimension.allowed_categories:
            distance = _categorical_distance(
                left_values[dimension.name],
                right_values[dimension.name],
                dimension,
            )
        else:
            distance = _numeric_distance(
                left_values[dimension.name],
                right_values[dimension.name],
                dimension,
            )
        distances.append(distance)
    return fmean(distances) if distances else 0.0


def _boundary_fraction(
    cards: tuple[ConfigurationEvaluationCard, ...],
    registry: ParameterSpaceRegistry,
    tolerance: float,
) -> float:
    checks = 0
    boundaries = 0
    for card in cards:
        values = card.parameter_map()
        for dimension in registry.dimensions:
            if dimension.allowed_categories:
                continue
            checks += 1
            if dimension.numeric_minimum is None or dimension.numeric_maximum is None:
                raise ContractError(f"numeric parameter {dimension.name} lacks bounds")
            value = values[dimension.name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"numeric parameter {dimension.name} requires numeric values")
            scale = dimension.numeric_maximum - dimension.numeric_minimum
            normalized = (float(value) - dimension.numeric_minimum) / scale
            if normalized <= tolerance or normalized >= 1.0 - tolerance:
                boundaries += 1
    return 0.0 if checks == 0 else boundaries / checks


def _connected_components(
    cards: tuple[ConfigurationEvaluationCard, ...],
    registry: ParameterSpaceRegistry,
    radius: float,
) -> tuple[tuple[ConfigurationEvaluationCard, ...], ...]:
    by_id = {card.configuration_id: card for card in cards}
    adjacency: dict[str, set[str]] = {card.configuration_id: set() for card in cards}
    for index, left in enumerate(cards):
        for right in cards[index + 1 :]:
            if _parameter_distance(left, right, registry) <= radius:
                adjacency[left.configuration_id].add(right.configuration_id)
                adjacency[right.configuration_id].add(left.configuration_id)
    seen: set[str] = set()
    components: list[tuple[ConfigurationEvaluationCard, ...]] = []
    for configuration_id in sorted(by_id):
        if configuration_id in seen:
            continue
        queue: deque[str] = deque([configuration_id])
        members: list[ConfigurationEvaluationCard] = []
        seen.add(configuration_id)
        while queue:
            current = queue.popleft()
            members.append(by_id[current])
            for neighbor in sorted(adjacency[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(tuple(sorted(members, key=lambda item: item.configuration_id)))
    return tuple(components)


def _build_regions(
    cards: tuple[ConfigurationEvaluationCard, ...],
    registry: ParameterSpaceRegistry,
    objective: CompetitionObjectivePolicy,
    build_policy: FrontierBuildPolicy,
) -> tuple[ParameterRegion, ...]:
    regions: list[ParameterRegion] = []
    for component in _connected_components(cards, registry, build_policy.neighbor_radius):
        utilities = [configuration_utility(card, objective) for card in component]
        dispersion = 0.0 if len(utilities) == 1 else pstdev(utilities)
        is_large_enough = len(component) >= build_policy.minimum_region_size
        is_stable_enough = dispersion <= build_policy.maximum_utility_dispersion
        if is_large_enough and is_stable_enough:
            state = ParameterRegionState.ROBUST_PLATEAU
        elif len(component) == 1:
            state = ParameterRegionState.FRAGILE_PEAK
        else:
            state = ParameterRegionState.SPARSE_REGION
        lower_bounds = [
            card.metric_map()[build_policy.primary_lower_bound_metric_id]
            for card in component
            if build_policy.primary_lower_bound_metric_id in card.metric_map()
        ]
        if not lower_bounds:
            raise ValueError("eligible parameter regions require a primary lower-bound metric")
        member_ids = tuple(card.configuration_id for card in component)
        region_id = f"region-{sha256_hex(member_ids)[:12]}"
        regions.append(
            ParameterRegion(
                region_id=region_id,
                cohort_id=component[0].cohort_id,
                member_configuration_ids=member_ids,
                state=state,
                mean_utility=fmean(utilities),
                minimum_primary_lower_bound=min(lower_bounds),
                utility_dispersion=dispersion,
                boundary_fraction=_boundary_fraction(
                    component,
                    registry,
                    build_policy.boundary_tolerance,
                ),
            )
        )
    return tuple(sorted(regions, key=lambda item: (-item.mean_utility, item.region_id)))


def build_robust_configuration_frontier(
    *,
    objective: CompetitionObjectivePolicy,
    configurations: tuple[ConfigurationEvaluationCard, ...],
    parameter_space: ParameterSpaceRegistry,
    model_confidence_set_ids: tuple[str, ...],
    build_policy: FrontierBuildPolicy | None = None,
) -> ModuleResult[RobustConfigurationFrontier]:
    """Build cohort-local Pareto frontiers and stable parameter regions."""

    build_policy = build_policy or FrontierBuildPolicy()
    mcs = set(model_confidence_set_ids)
    by_cohort: dict[str, list[ConfigurationEvaluationCard]] = defaultdict(list)
    for card in configurations:
        by_cohort[card.cohort_id].append(card)

    cohort_outputs: list[CohortFrontier] = []
    warnings: list[str] = []
    total_eligible = 0
    for cohort_id in sorted(by_cohort):
        cohort_cards = tuple(sorted(by_cohort[cohort_id], key=lambda item: item.configuration_id))
        eligible: list[ConfigurationEvaluationCard] = []
        ineligible: list[str] = []
        for card in cohort_cards:
            passes, reasons = _passes_hard_gates(card, objective)
            if mcs and card.configuration_id not in mcs:
                passes = False
                reasons = (*reasons, "not in Model Confidence Set")
            try:
                for axis in objective.frontier_axes:
                    _axis_value(card, axis)
                configuration_utility(card, objective)
                metrics = card.metric_map()
                if build_policy.primary_lower_bound_metric_id not in metrics:
                    raise KeyError(
                        f"configuration {card.configuration_id} lacks lower-bound metric "
                        f"{build_policy.primary_lower_bound_metric_id}"
                    )
                for tie_breaker in objective.tie_breakers:
                    if tie_breaker.metric_id not in metrics:
                        raise KeyError(
                            f"configuration {card.configuration_id} lacks tie-break metric "
                            f"{tie_breaker.metric_id}"
                        )
            except KeyError as error:
                passes = False
                reasons = (*reasons, str(error))
            if passes:
                eligible.append(card)
            else:
                ineligible.append(card.configuration_id)
                warnings.extend(f"{card.configuration_id}: {reason}" for reason in reasons)

        dominated_rows: list[DominatedConfiguration] = []
        frontier_cards: list[ConfigurationEvaluationCard] = []
        for candidate in eligible:
            dominators = tuple(
                other.configuration_id
                for other in eligible
                if other.configuration_id != candidate.configuration_id
                and _dominates(other, candidate, objective.frontier_axes)
            )
            if dominators:
                dominated_rows.append(
                    DominatedConfiguration(
                        configuration_id=candidate.configuration_id,
                        dominated_by=tuple(sorted(dominators)),
                        reason="strict Pareto dominance under committed frontier axes",
                    )
                )
            else:
                frontier_cards.append(candidate)

        regions = (
            _build_regions(tuple(frontier_cards), parameter_space, objective, build_policy)
            if frontier_cards
            else ()
        )
        total_eligible += len(eligible)
        cohort_outputs.append(
            CohortFrontier(
                cohort_id=cohort_id,
                frontier_configuration_ids=tuple(card.configuration_id for card in frontier_cards),
                eligible_configuration_ids=tuple(card.configuration_id for card in eligible),
                ineligible_configuration_ids=tuple(sorted(ineligible)),
                robust_regions=regions,
                dominated=tuple(sorted(dominated_rows, key=lambda item: item.configuration_id)),
            )
        )

    if total_eligible == 0:
        state = FrontierState.NO_ELIGIBLE_CONFIGURATION
        status = ModuleStatus.INSUFFICIENT_EVIDENCE
        reasons = ("P9_PROMOTION_NO_CONFIGURATION_PASSES_HARD_GATES",)
    else:
        robust_count = sum(
            region.state == ParameterRegionState.ROBUST_PLATEAU
            for cohort in cohort_outputs
            for region in cohort.robust_regions
        )
        fragile_count = sum(
            region.state == ParameterRegionState.FRAGILE_PEAK
            for cohort in cohort_outputs
            for region in cohort.robust_regions
        )
        if robust_count > 1:
            state = FrontierState.MULTIPLE_ROBUST_REGIONS
        elif robust_count == 0 and fragile_count > 0:
            state = FrontierState.PARAMETER_REGION_FRAGILE
        else:
            state = FrontierState.FRONTIER_AVAILABLE
        status = ModuleStatus.SUCCESS
        reasons = ()

    output = RobustConfigurationFrontier(
        state=state,
        cohorts=tuple(cohort_outputs),
        warnings=tuple(sorted(set(warnings))),
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=output,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("configuration_count", len(configurations)),
                ("eligible_configuration_count", total_eligible),
                (
                    "frontier_configuration_count",
                    sum(len(cohort.frontier_configuration_ids) for cohort in cohort_outputs),
                ),
            ),
            trace=("cohort-local hard gates, Pareto dominance, and parameter regions evaluated",),
        ),
        reason_codes=reasons,
    )
