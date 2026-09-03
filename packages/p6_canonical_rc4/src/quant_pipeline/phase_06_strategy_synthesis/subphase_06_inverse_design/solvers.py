"""Stable facade for bounded CPU-first strategy solvers."""

from __future__ import annotations

from ..domain.enums import SolverMethod
from ..domain.models import SolverResult
from .solver_common import (
    solver_data,
    synthesis_problems,
    unavailable_result,
)
from .solver_exact import solve_continuous, solve_integer
from .solver_search import solve_beam, solve_evolutionary, solve_local


def continuous_results(problems, basis, configuration):
    basis_by_id = {item.basis_id: item for item in basis}
    return tuple(
        solve_continuous(solver_data(problem, basis_by_id), configuration)
        for problem in problems
    )


def integer_results(problems, basis, continuous, configuration):
    basis_by_id = {item.basis_id: item for item in basis}
    seed_by_problem = {item.problem_id: item for item in continuous}
    return tuple(
        solve_integer(
            solver_data(problem, basis_by_id),
            seed_by_problem.get(problem.problem_id),
            configuration,
        )
        for problem in problems
    )


def beam_results(problems, basis, configuration):
    basis_by_id = {item.basis_id: item for item in basis}
    return tuple(
        solve_beam(solver_data(problem, basis_by_id), configuration)
        for problem in problems
    )


def local_results(problems, basis, seeds, configuration):
    basis_by_id = {item.basis_id: item for item in basis}
    grouped: dict[str, list[SolverResult]] = {}
    for seed in seeds:
        grouped.setdefault(seed.problem_id, []).append(seed)
    return tuple(
        solve_local(
            solver_data(problem, basis_by_id),
            grouped.get(problem.problem_id, []),
            configuration,
        )
        for problem in problems
    )


def evolutionary_results(problems, basis, configuration):
    basis_by_id = {item.basis_id: item for item in basis}
    if not configuration.operational_mode.challenger_enabled:
        return tuple(
            unavailable_result(
                problem,
                SolverMethod.EVOLUTIONARY_CHALLENGER,
                configuration,
            )
            for problem in problems
        )
    return tuple(
        solve_evolutionary(solver_data(problem, basis_by_id), configuration)
        for problem in problems
    )


__all__ = (
    "beam_results",
    "continuous_results",
    "evolutionary_results",
    "integer_results",
    "local_results",
    "synthesis_problems",
)
