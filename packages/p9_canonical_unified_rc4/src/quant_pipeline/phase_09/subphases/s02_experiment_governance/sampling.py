from __future__ import annotations

import math
import random
from collections.abc import Iterator, Mapping, Sequence

from .conditions import parameter_is_active
from .contracts.parameters import ParameterScalar
from .contracts.search_space import CompiledParameterDomain, CompiledSearchSpace


def finite_domain_values(domain: CompiledParameterDomain) -> tuple[ParameterScalar, ...]:
    if domain.discrete_values:
        return domain.discrete_values
    if domain.grid_points is None or domain.lower is None or domain.upper is None:
        raise ValueError(f"parameter {domain.parameter_id} does not have finite grid values")
    count = domain.grid_points
    if domain.scale.value == "LOG":
        start = math.log(float(domain.lower))
        stop = math.log(float(domain.upper))
        raw = [math.exp(start + (stop - start) * index / (count - 1)) for index in range(count)]
    else:
        raw = [
            float(domain.lower)
            + (float(domain.upper) - float(domain.lower)) * index / (count - 1)
            for index in range(count)
        ]
    if domain.kind.value == "INTEGER":
        values = tuple(dict.fromkeys(int(round(value)) for value in raw))
        if len(values) < 2:
            raise ValueError(f"integer grid for {domain.parameter_id} collapsed to one value")
        return values
    return tuple(raw)


def iter_grid_assignments(space: CompiledSearchSpace) -> Iterator[dict[str, ParameterScalar]]:
    domains = {parameter.parameter_id: parameter for parameter in space.parameters}
    order = space.constraint_graph.parameter_order

    def walk(
        index: int,
        current: dict[str, ParameterScalar],
    ) -> Iterator[dict[str, ParameterScalar]]:
        if index == len(order):
            yield dict(current)
            return
        parameter_id = order[index]
        domain = domains[parameter_id]
        if not parameter_is_active(domain.active_when, current):
            yield from walk(index + 1, current)
            return
        for value in finite_domain_values(domain):
            current[parameter_id] = value
            yield from walk(index + 1, current)
        current.pop(parameter_id, None)

    yield from walk(0, {})


def _sample_domain_value(
    domain: CompiledParameterDomain,
    rng: random.Random,
) -> ParameterScalar:
    if domain.discrete_values:
        return rng.choice(domain.discrete_values)
    if domain.lower is None or domain.upper is None:
        raise ValueError(f"numeric bounds missing for {domain.parameter_id}")
    lower = float(domain.lower)
    upper = float(domain.upper)
    if domain.scale.value == "LOG":
        value = math.exp(rng.uniform(math.log(lower), math.log(upper)))
    else:
        value = rng.uniform(lower, upper)
    if domain.kind.value == "INTEGER":
        return int(round(value))
    return value


def sample_random_assignment(
    space: CompiledSearchSpace,
    rng: random.Random,
) -> dict[str, ParameterScalar]:
    domains = {parameter.parameter_id: parameter for parameter in space.parameters}
    assignments: dict[str, ParameterScalar] = {}
    for parameter_id in space.constraint_graph.parameter_order:
        domain = domains[parameter_id]
        if parameter_is_active(domain.active_when, assignments):
            assignments[parameter_id] = _sample_domain_value(domain, rng)
    return assignments


def assignment_key(assignments: Mapping[str, ParameterScalar]) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(assignments.items()))


def take_unique_random_assignments(
    space: CompiledSearchSpace,
    *,
    count: int,
    seed: int,
    maximum_attempt_multiplier: int = 50,
) -> tuple[dict[str, ParameterScalar], ...]:
    rng = random.Random(seed)
    seen: set[tuple[tuple[str, object], ...]] = set()
    results: list[dict[str, ParameterScalar]] = []
    maximum_attempts = max(count * maximum_attempt_multiplier, 100)
    for _ in range(maximum_attempts):
        assignment = sample_random_assignment(space, rng)
        key = assignment_key(assignment)
        if key in seen:
            continue
        seen.add(key)
        results.append(assignment)
        if len(results) == count:
            break
    return tuple(results)


def boundary_parameter_ids(
    assignment: Mapping[str, ParameterScalar],
    domains: Sequence[CompiledParameterDomain],
) -> tuple[str, ...]:
    boundaries: list[str] = []
    for domain in domains:
        if domain.parameter_id not in assignment:
            continue
        value = assignment[domain.parameter_id]
        if domain.discrete_values:
            if value in {domain.discrete_values[0], domain.discrete_values[-1]}:
                boundaries.append(domain.parameter_id)
        elif domain.lower is not None and domain.upper is not None:
            if value == domain.lower or value == domain.upper:
                boundaries.append(domain.parameter_id)
    return tuple(sorted(boundaries))
