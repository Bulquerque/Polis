"""Small deterministic graph algorithms without runtime graph-library dependencies."""
from __future__ import annotations

from collections import Counter, deque
import math
from typing import Iterable

from .models import SocialEdge, SocialNode

Pair = tuple[str, str]


def canonical_pair(left: str, right: str) -> Pair:
    return (left, right) if left < right else (right, left)


def pair_set(edges: Iterable[SocialEdge]) -> set[Pair]:
    return {canonical_pair(edge.source_person_id, edge.target_person_id) for edge in edges}


def adjacency(node_ids: Iterable[str], pairs: Iterable[Pair]) -> dict[str, set[str]]:
    result = {node_id: set() for node_id in node_ids}
    for left, right in pairs:
        result[left].add(right)
        result[right].add(left)
    return result


def connected_components(node_ids: Iterable[str], pairs: Iterable[Pair]) -> tuple[tuple[str, ...], ...]:
    graph = adjacency(node_ids, pairs)
    remaining = set(graph)
    components: list[tuple[str, ...]] = []
    while remaining:
        start = min(remaining)
        queue = deque([start])
        seen = {start}
        remaining.remove(start)
        while queue:
            node = queue.popleft()
            for neighbor in sorted(graph[node]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    remaining.discard(neighbor)
                    queue.append(neighbor)
        components.append(tuple(sorted(seen)))
    return tuple(sorted(components, key=lambda item: (len(item), item), reverse=True))


def degrees(node_ids: Iterable[str], pairs: Iterable[Pair]) -> dict[str, int]:
    graph = adjacency(node_ids, pairs)
    return {node: len(neighbors) for node, neighbors in sorted(graph.items())}


def hub_share(degree_map: dict[str, int]) -> float:
    total = math.fsum(degree_map.values())
    return 0.0 if total == 0.0 else max(degree_map.values(), default=0) / total


def pair_counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))
