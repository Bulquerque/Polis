from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence

from .contracts.base import ConditionOperator
from .contracts.parameters import ParameterScalar
from .contracts.search_space import ActivationCondition, SearchSpaceConstraintEdge


def condition_matches(
    condition: ActivationCondition,
    assignments: Mapping[str, ParameterScalar],
) -> bool:
    if condition.parent_parameter_id not in assignments:
        return False
    current = assignments[condition.parent_parameter_id]
    values = condition.values
    if condition.operator is ConditionOperator.EQUALS:
        return current == values[0]
    if condition.operator is ConditionOperator.NOT_EQUALS:
        return current != values[0]
    if condition.operator is ConditionOperator.IN:
        return current in values
    if condition.operator is ConditionOperator.NOT_IN:
        return current not in values
    raise ValueError(f"unsupported operator: {condition.operator}")


def parameter_is_active(
    conditions: Sequence[ActivationCondition],
    assignments: Mapping[str, ParameterScalar],
) -> bool:
    return all(condition_matches(condition, assignments) for condition in conditions)


def topological_parameter_order(
    parameter_ids: Sequence[str],
    edges: Sequence[SearchSpaceConstraintEdge],
) -> tuple[str, ...]:
    nodes = set(parameter_ids)
    incoming: dict[str, int] = {node: 0 for node in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.parent_parameter_id not in nodes or edge.child_parameter_id not in nodes:
            raise ValueError("condition edge references unknown parameter")
        children[edge.parent_parameter_id].append(edge.child_parameter_id)
        incoming[edge.child_parameter_id] += 1
    ready = deque(sorted(node for node, count in incoming.items() if count == 0))
    ordered: list[str] = []
    while ready:
        node = ready.popleft()
        ordered.append(node)
        for child in sorted(children[node]):
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
    if len(ordered) != len(nodes):
        raise ValueError("conditional parameter graph contains a cycle")
    return tuple(ordered)
