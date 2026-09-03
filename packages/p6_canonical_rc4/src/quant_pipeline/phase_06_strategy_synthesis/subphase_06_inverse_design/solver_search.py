"""Deterministic beam, local, and evolutionary search solvers."""

from __future__ import annotations

from random import Random

from ..domain.enums import SolverMethod, SolverStatus
from ..domain.models import SolverResult
from ..foundation.configuration import Phase6RunConfiguration
from .solver_budget import SolverBudget
from .solver_common import SolverData, objective, result_record


def solve_beam(data: SolverData, configuration: Phase6RunConfiguration) -> SolverResult:
    budget = SolverBudget.for_problem(data, configuration)
    initial = tuple(0.0 for _ in data.basis)
    if not budget.consume():
        return result_record(
            data,
            SolverMethod.BEAM_SEARCH,
            SolverStatus.TIMEOUT,
            initial,
            None,
            0,
            budget.nodes,
            configuration,
            budget.diagnostics(),
        )
    beam = [(objective(data, initial, configuration), initial)]
    depth_limit = min(configuration.solver.beam_depth, data.problem.max_legs)
    depth = 0
    for depth in range(depth_limit):
        expanded: dict[tuple[float, ...], float] = {}
        for _, state in beam:
            for index in range(len(data.basis)):
                if state[index] >= data.problem.max_quantity:
                    continue
                child = list(state)
                child[index] += 1.0
                values = tuple(child)
                if sum(value != 0 for value in values) > data.problem.max_legs:
                    continue
                if not budget.consume():
                    break
                expanded[values] = objective(data, values, configuration)
            if budget.exhausted:
                break
        beam = sorted(
            (score, state) for state, score in expanded.items()
        )[: configuration.solver.beam_width]
        if not beam or budget.exhausted:
            break
    best, state = min(beam) if beam else (objective(data, initial, configuration), initial)
    status = (
        SolverStatus.TIMEOUT
        if budget.exhausted
        and (budget.expired or budget.nodes >= budget.node_limit or not budget.memory_ok)
        else SolverStatus.FEASIBLE
    )
    return result_record(
        data,
        SolverMethod.BEAM_SEARCH,
        status,
        state,
        best,
        depth + 1,
        budget.nodes,
        configuration,
        budget.diagnostics(),
    )


def solve_local(data: SolverData, seeds: list[SolverResult], configuration: Phase6RunConfiguration) -> SolverResult:
    budget = SolverBudget.for_problem(data, configuration)
    quantities = _seed_quantities(data, seeds)
    if not budget.consume():
        return result_record(
            data,
            SolverMethod.LOCAL_SEARCH,
            SolverStatus.TIMEOUT,
            tuple(quantities),
            None,
            0,
            budget.nodes,
            configuration,
            budget.diagnostics(),
        )
    best = objective(data, tuple(quantities), configuration)
    passes = 0
    for _ in range(configuration.solver.local_search_iterations):
        changed = False
        for index in range(len(data.basis)):
            for delta in (-1.0, 1.0):
                value = quantities[index] + delta
                if value < 0 or value > data.problem.max_quantity:
                    continue
                child = quantities.copy()
                child[index] = value
                if sum(item != 0 for item in child) > data.problem.max_legs:
                    continue
                if not budget.consume():
                    break
                score = objective(data, tuple(child), configuration)
                if score + 1e-12 < best:
                    quantities, best, changed = child, score, True
            if budget.exhausted:
                break
        passes += 1
        if not changed or budget.exhausted:
            break
    status = (
        SolverStatus.TIMEOUT
        if budget.exhausted
        and (budget.expired or budget.nodes >= budget.node_limit or not budget.memory_ok)
        else SolverStatus.FEASIBLE
    )
    return result_record(
        data,
        SolverMethod.LOCAL_SEARCH,
        status,
        tuple(quantities),
        best,
        passes,
        budget.nodes,
        configuration,
        budget.diagnostics(),
    )


def solve_evolutionary(data: SolverData, configuration: Phase6RunConfiguration) -> SolverResult:
    budget = SolverBudget.for_problem(data, configuration)
    random = Random(configuration.seed + int(data.problem.problem_id[-6:], 16))
    population = _initial_population(data, configuration, budget, random)
    if not population:
        empty = tuple(0.0 for _ in data.basis)
        return result_record(
            data,
            SolverMethod.EVOLUTIONARY_CHALLENGER,
            SolverStatus.TIMEOUT,
            empty,
            None,
            0,
            budget.nodes,
            configuration,
            budget.diagnostics(),
        )
    generations_done = 0
    for _ in range(configuration.solver.evolutionary_generations):
        population = _evolve_generation(
            data, configuration, budget, random, population
        )
        generations_done += 1
        if budget.exhausted:
            break
    best, state = min(
        (objective(data, item, configuration), item) for item in population
    )
    status = _budget_status(budget)
    diagnostics = ("CHALLENGER_NON_BLOCKING",) + budget.diagnostics()
    return result_record(
        data,
        SolverMethod.EVOLUTIONARY_CHALLENGER,
        status,
        state,
        best,
        generations_done,
        budget.nodes,
        configuration,
        diagnostics,
    )


def _initial_population(data, configuration, budget, random):
    population = []
    size = configuration.solver.evolutionary_population
    count = len(data.basis)
    while len(population) < size and budget.consume():
        state = [0.0] * count
        sample_size = min(data.problem.max_legs, count)
        for index in random.sample(range(count), k=sample_size):
            if random.random() < 0.5:
                state[index] = float(random.randint(1, data.problem.max_quantity))
        population.append(tuple(state))
    return population


def _evolve_generation(data, configuration, budget, random, population):
    ranked = sorted(
        (objective(data, item, configuration), item) for item in population
    )
    survivor_count = max(1, len(ranked) // 2)
    survivors = [item for _, item in ranked[:survivor_count]]
    output = survivors.copy()
    while len(output) < configuration.solver.evolutionary_population:
        if not budget.consume():
            break
        child = list(random.choice(survivors))
        index = random.randrange(len(data.basis))
        child[index] = float(random.randint(0, data.problem.max_quantity))
        _repair_leg_count(child, data.problem.max_legs, random)
        output.append(tuple(child))
    return output


def _budget_status(budget):
    exhausted = (
        budget.expired
        or budget.nodes >= budget.node_limit
        or not budget.memory_ok
    )
    return SolverStatus.TIMEOUT if budget.exhausted and exhausted else SolverStatus.FEASIBLE


def _expand_beam(data, beam, configuration):
    """Compatibility helper with strict local node accounting."""
    expanded = {}
    nodes = 0
    for _, state in beam:
        for index in range(len(data.basis)):
            if nodes >= configuration.budgets.max_solver_nodes:
                break
            if state[index] >= data.problem.max_quantity:
                continue
            child = list(state)
            child[index] += 1.0
            values = tuple(child)
            if sum(value != 0 for value in values) > data.problem.max_legs:
                continue
            expanded[values] = objective(data, values, configuration)
            nodes += 1
    ranked = sorted((score, state) for state, score in expanded.items())
    return ranked[: configuration.solver.beam_width], nodes


def _seed_quantities(data, seeds):
    available = [item for item in seeds if item.objective_value is not None]
    seed = min(available, key=lambda item: item.objective_value, default=None)
    if seed is None:
        return [0.0] * len(data.basis)
    mapping = {item.basis_id: float(item.quantity) for item in seed.quantities}
    return [mapping.get(item.basis_id, 0.0) for item in data.basis]


def _repair_leg_count(values, max_legs, random):
    while sum(value != 0 for value in values) > max_legs:
        nonzero = [
            index
            for index, value in enumerate(values)
            if value != 0
        ]
        values[random.choice(nonzero)] = 0.0
