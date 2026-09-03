"""Shared data and accounting for bounded strategy solvers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..domain.enums import SolverMethod, SolverStatus
from ..domain.models import (
    ReplicationBasisInstrument,
    SolverQuantity,
    SolverResult,
    StrategySynthesisProblem,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id


@dataclass(frozen=True)
class SolverData:
    problem: StrategySynthesisProblem
    basis: tuple[ReplicationBasisInstrument, ...]
    x: tuple[tuple[float, ...], ...]
    y: tuple[float, ...]
    w: tuple[float, ...]


def synthesis_problems(targets, qualifications, basis, configuration):
    """Create one constrained synthesis problem for each qualified target."""
    qualified = {
        item.target_payoff_id
        for item in qualifications
        if item.qualified
    }
    by_target: dict[str, list[ReplicationBasisInstrument]] = {}
    for item in basis:
        by_target.setdefault(item.target_payoff_id, []).append(item)
    output = []
    for target in targets:
        items = tuple(by_target.get(target.target_payoff_id, ()))
        if target.target_payoff_id not in qualified or not items:
            continue
        basis_ids = tuple(item.basis_id for item in items)
        output.append(
            StrategySynthesisProblem(
                problem_id=stable_id(
                    "synthesis-problem",
                    target.target_payoff_id,
                    basis_ids,
                ),
                target_payoff_id=target.target_payoff_id,
                underlying_id=target.underlying_id,
                state_grid=target.terminal_state_grid,
                target_vector=target.regularized_target_payoff,
                scenario_weights=target.scenario_probabilities,
                basis_ids=basis_ids,
                max_legs=configuration.budgets.max_legs,
                max_quantity=configuration.budgets.max_quantity,
                cost_budget=target.cost_budget,
                risk_budget=target.risk_budget,
            )
        )
    return tuple(output)


def solver_data(problem, basis_by_id) -> SolverData:
    """Build dense numeric vectors without changing source records."""
    items = tuple(
        basis_by_id[item]
        for item in problem.basis_ids
        if item in basis_by_id
    )
    x = tuple(
        tuple(float(value) for value in item.payoff_vector)
        for item in items
    )
    return SolverData(
        problem=problem,
        basis=items,
        x=x,
        y=tuple(float(value) for value in problem.target_vector),
        w=tuple(float(value) for value in problem.scenario_weights),
    )


def objective(
    data: SolverData,
    quantities: tuple[float, ...],
    configuration: Phase6RunConfiguration,
) -> float:
    """Evaluate weighted approximation error and bounded penalties."""
    predicted = [
        sum(
            data.x[column][row] * quantities[column]
            for column in range(len(quantities))
        )
        for row in range(len(data.y))
    ]
    error = sum(
        weight * (left - right) ** 2
        for weight, left, right in zip(data.w, predicted, data.y)
    )
    l1 = float(configuration.solver.l1_penalty) * sum(
        abs(value)
        for value in quantities
    )
    complexity = float(configuration.solver.complexity_penalty) * sum(
        value != 0
        for value in quantities
    )
    return error + l1 + complexity + side_conflicts(data, quantities) * 1e12


def side_conflicts(
    data: SolverData,
    quantities: tuple[float, ...],
) -> int:
    """Count instruments selected on both long and short basis sides."""
    sides: dict[str, set[str]] = {}
    for basis, quantity in zip(data.basis, quantities):
        if abs(quantity) <= 1e-12:
            continue
        sides.setdefault(basis.instrument_id, set()).add(basis.leg.side.value)
    return sum(len(values) > 1 for values in sides.values())


def result_record(
    data: SolverData,
    method: SolverMethod,
    status: SolverStatus,
    quantities: tuple[float, ...],
    objective_value: float | None,
    iterations: int,
    nodes: int,
    configuration: Phase6RunConfiguration,
    diagnostics: tuple[str, ...] = (),
) -> SolverResult:
    """Build a deterministic solver record; runtime stays in diagnostics logs."""
    nonzero = tuple(
        SolverQuantity(
            basis_id=item.basis_id,
            quantity=Decimal(str(value)),
        )
        for item, value in zip(data.basis, quantities)
        if abs(value) > 1e-12
    )
    return SolverResult(
        solver_result_id=stable_id(
            "solver-result",
            data.problem.problem_id,
            method,
            nonzero,
            objective_value,
        ),
        problem_id=data.problem.problem_id,
        target_payoff_id=data.problem.target_payoff_id,
        method=method,
        solver_name=f"P6_{method.value}",
        solver_version="1.0",
        status=status,
        quantities=nonzero,
        objective_value=(
            None
            if objective_value is None
            else Decimal(str(objective_value))
        ),
        best_bound=(
            Decimal(str(objective_value))
            if objective_value is not None and status is SolverStatus.OPTIMAL
            else None
        ),
        optimality_gap=(Decimal("0") if status is SolverStatus.OPTIMAL else None),
        runtime_ms=0,
        iterations=iterations,
        node_count=nodes,
        timeout=status is SolverStatus.TIMEOUT,
        seed=configuration.seed,
        diagnostics=diagnostics,
    )


def unavailable_result(
    problem: StrategySynthesisProblem,
    method: SolverMethod,
    configuration: Phase6RunConfiguration,
) -> SolverResult:
    data = SolverData(problem=problem, basis=(), x=(), y=(), w=())
    return result_record(
        data,
        method,
        SolverStatus.UNAVAILABLE,
        (),
        None,
        0,
        0,
        configuration,
        ("DISABLED_BY_OPERATIONAL_MODE",),
    )
