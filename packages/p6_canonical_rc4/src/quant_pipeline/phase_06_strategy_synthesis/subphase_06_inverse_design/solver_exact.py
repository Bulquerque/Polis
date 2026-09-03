"""Continuous relaxation and bounded integer enumeration solvers."""

from __future__ import annotations

from itertools import product
from time import monotonic

from ..domain.enums import SolverMethod, SolverStatus
from ..domain.models import SolverResult
from ..foundation.configuration import Phase6RunConfiguration
from .solver_budget import SolverBudget
from .solver_common import SolverData, objective, result_record


def solve_continuous(
    data: SolverData,
    configuration: Phase6RunConfiguration,
) -> SolverResult:
    """Run deterministic non-negative coordinate descent."""
    started_at = monotonic()
    budget = SolverBudget.for_problem(data, configuration)
    count = len(data.basis)
    if not budget.memory_ok:
        values = tuple(0.0 for _ in data.basis)
        return result_record(
            data,
            SolverMethod.CONTINUOUS_RELAXATION,
            SolverStatus.TIMEOUT,
            values,
            None,
            0,
            0,
            configuration,
            budget.diagnostics(),
        )
    quantities = [0.0] * count
    iterations = configuration.solver.continuous_iterations
    for iteration in range(iterations):
        _coordinate_pass(data, quantities)
        if _timed_out(started_at, configuration):
            values = tuple(quantities)
            return result_record(
                data,
                SolverMethod.CONTINUOUS_RELAXATION,
                SolverStatus.TIMEOUT,
                values,
                objective(data, values, configuration),
                iteration + 1,
                0,
                configuration,
            )
    values = tuple(quantities)
    return result_record(
        data,
        SolverMethod.CONTINUOUS_RELAXATION,
        SolverStatus.FEASIBLE,
        values,
        objective(data, values, configuration),
        iterations,
        0,
        configuration,
    )


def solve_integer(
    data: SolverData,
    seed: SolverResult | None,
    configuration: Phase6RunConfiguration,
) -> SolverResult:
    """Search a bounded integer neighborhood around the continuous seed."""
    started_at = monotonic()
    budget = SolverBudget.for_problem(data, configuration)
    if not budget.memory_ok:
        empty = tuple(0.0 for _ in data.basis)
        return result_record(
            data,
            SolverMethod.BOUNDED_INTEGER_NEIGHBORHOOD,
            SolverStatus.TIMEOUT,
            empty,
            None,
            0,
            0,
            configuration,
            budget.diagnostics(),
        )
    seed_map = _seed_map(seed)
    ordered = _ordered_basis(data, seed_map)
    options = _integer_options(data, ordered, seed_map)
    best_quantities = tuple(0.0 for _ in data.basis)
    best_objective = objective(data, best_quantities, configuration)
    nodes = 0
    timed_out = False
    combinations = product(*options) if options else [()]
    for combination in combinations:
        if _node_limit(nodes, started_at, configuration):
            timed_out = True
            break
        nodes += 1
        quantities = _combination_quantities(
            len(data.basis),
            ordered,
            combination,
        )
        if sum(value != 0 for value in quantities) > data.problem.max_legs:
            continue
        score = objective(data, quantities, configuration)
        if score < best_objective:
            best_objective = score
            best_quantities = quantities
    status = SolverStatus.TIMEOUT if timed_out else SolverStatus.FEASIBLE
    return result_record(
        data,
        SolverMethod.BOUNDED_INTEGER_NEIGHBORHOOD,
        status,
        best_quantities,
        best_objective,
        nodes,
        nodes,
        configuration,
        ("LOCAL_INTEGER_NEIGHBORHOOD_NO_GLOBAL_OPTIMALITY_CERTIFICATE",),
    )


def _coordinate_pass(data: SolverData, quantities: list[float]) -> None:
    for column in range(len(data.basis)):
        residual = [
            data.y[row]
            - sum(
                data.x[other][row] * quantities[other]
                for other in range(len(data.basis))
                if other != column
            )
            for row in range(len(data.y))
        ]
        denominator = sum(
            data.w[row] * data.x[column][row] ** 2
            for row in range(len(data.y))
        )
        numerator = sum(
            data.w[row] * data.x[column][row] * residual[row]
            for row in range(len(data.y))
        )
        value = 0.0 if denominator <= 1e-18 else numerator / denominator
        upper = float(data.basis[column].quantity_upper_bound)
        quantities[column] = min(max(value, 0.0), upper)


def _seed_map(seed: SolverResult | None) -> dict[str, float]:
    if seed is None:
        return {}
    return {
        item.basis_id: float(item.quantity)
        for item in seed.quantities
    }


def _ordered_basis(
    data: SolverData,
    seed_map: dict[str, float],
) -> tuple[int, ...]:
    indices = sorted(
        range(len(data.basis)),
        key=lambda index: (
            -abs(seed_map.get(data.basis[index].basis_id, 0.0)),
            data.basis[index].basis_id,
        ),
    )
    return tuple(indices[: min(data.problem.max_legs, len(indices))])


def _integer_options(
    data: SolverData,
    ordered: tuple[int, ...],
    seed_map: dict[str, float],
) -> tuple[tuple[int, ...], ...]:
    output = []
    for index in ordered:
        center = int(
            round(seed_map.get(data.basis[index].basis_id, 0.0))
        )
        values = {
            0,
            1,
            max(0, center - 1),
            center,
            min(data.problem.max_quantity, center + 1),
        }
        output.append(tuple(sorted(values)))
    return tuple(output)


def _combination_quantities(
    count: int,
    ordered: tuple[int, ...],
    combination: tuple[int, ...],
) -> tuple[float, ...]:
    quantities = [0.0] * count
    for index, value in zip(ordered, combination):
        quantities[index] = float(value)
    return tuple(quantities)


def _timed_out(
    started_at: float,
    configuration: Phase6RunConfiguration,
) -> bool:
    limit = configuration.budgets.max_solver_seconds
    return bool(limit > 0 and monotonic() - started_at > limit)


def _node_limit(
    nodes: int,
    started_at: float,
    configuration: Phase6RunConfiguration,
) -> bool:
    if nodes >= configuration.budgets.max_solver_nodes:
        return True
    return _timed_out(started_at, configuration)
