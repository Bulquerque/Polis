
"""P8.S2.M02 — build a deterministic typed structural exposure graph."""

from __future__ import annotations

from collections import defaultdict, deque

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256

from ..context import S2ExecutionContext
from ..contracts.enums import ExposureNodeType, ExposureRelationType
from ..contracts.graph import ExposureEdge, ExposureNode, GraphComponent, StructuralExposureGraph
from ..contracts.results import M02Result
from ..errors import GraphIntegrityError
from ..module_support import build_receipt, seal

MODULE_ID = "P8.S2.M02"


def _node_id(kind: ExposureNodeType, value: str) -> str:
    return f"{kind.value.lower()}:{value}"


def _edge_id(source: str, target: str, relation: ExposureRelationType, suffix: str = "") -> str:
    digest = canonical_sha256((source, target, relation.value, suffix))[:20]
    return f"edge:{relation.value.lower()}:{digest}"


def _components(nodes: tuple[ExposureNode, ...], edges: tuple[ExposureEdge, ...]) -> tuple[GraphComponent, ...]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        adjacency[node.node_id]
    connectivity_relations = {
        ExposureRelationType.CANDIDATE_HAS_LEG,
        ExposureRelationType.CANDIDATE_UNDERLYING_SCOPE,
        ExposureRelationType.INSTRUMENT_EXPIRATION,
        ExposureRelationType.SAME_INSTRUMENT,
        ExposureRelationType.OPPOSITE_LEG,
        ExposureRelationType.SAME_EXPIRATION,
        ExposureRelationType.SAME_UNDERLYING_SCOPE,
    }
    for edge in edges:
        if edge.relation not in connectivity_relations:
            continue
        adjacency[edge.source_node_id].add(edge.target_node_id)
        adjacency[edge.target_node_id].add(edge.source_node_id)
    unseen = set(adjacency)
    result: list[GraphComponent] = []
    while unseen:
        start = min(unseen)
        queue = deque([start])
        collected: list[str] = []
        unseen.remove(start)
        while queue:
            current = queue.popleft()
            collected.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        node_ids = tuple(sorted(collected))
        result.append(GraphComponent(
            component_id=f"component:{canonical_sha256(node_ids)[:20]}",
            node_ids=node_ids,
        ))
    return tuple(sorted(result, key=lambda item: item.component_id))


def run_module(bundle, m01, *, context: S2ExecutionContext) -> M02Result:
    handoff = bundle.validated_handoff.handoff
    groups = {row.comparison_group_id: row for row in handoff.comparison_groups}
    node_map: dict[str, ExposureNode] = {}
    edges: list[ExposureEdge] = []

    def add_node(kind: ExposureNodeType, value: str) -> str:
        node_id = _node_id(kind, value)
        node_map[node_id] = ExposureNode(node_id=node_id, node_type=kind, label=value)
        return node_id

    for candidate in m01.normalized_intents.candidates:
        candidate_node = add_node(ExposureNodeType.CANDIDATE, candidate.candidate_id)
        group_node = add_node(ExposureNodeType.COMPARISON_GROUP, candidate.comparison_group_id)
        objective_node = add_node(ExposureNodeType.OBJECTIVE_FAMILY, candidate.objective_family)
        family_node = add_node(ExposureNodeType.CANDIDATE_FAMILY, candidate.candidate_family)
        currency_node = add_node(ExposureNodeType.CURRENCY, candidate.currency)
        fixed_edges = (
            (group_node, ExposureRelationType.CANDIDATE_IN_GROUP),
            (objective_node, ExposureRelationType.CANDIDATE_OBJECTIVE_FAMILY),
            (family_node, ExposureRelationType.CANDIDATE_FAMILY),
            (currency_node, ExposureRelationType.CANDIDATE_CURRENCY),
        )
        for target, relation in fixed_edges:
            edges.append(ExposureEdge(
                edge_id=_edge_id(candidate_node, target, relation),
                source_node_id=candidate_node,
                target_node_id=target,
                relation=relation,
            ))
        group = groups.get(candidate.comparison_group_id)
        if group is None:
            raise GraphIntegrityError(f"candidate comparison group is missing: {candidate.candidate_id}")
        for underlying in sorted(group.underlying_scope):
            target = add_node(ExposureNodeType.UNDERLYING_SCOPE, underlying)
            relation = ExposureRelationType.CANDIDATE_UNDERLYING_SCOPE
            edges.append(ExposureEdge(
                edge_id=_edge_id(candidate_node, target, relation),
                source_node_id=candidate_node,
                target_node_id=target,
                relation=relation,
            ))
        for leg in candidate.legs:
            instrument_node = add_node(ExposureNodeType.INSTRUMENT, leg.instrument_id)
            relation = ExposureRelationType.CANDIDATE_HAS_LEG
            edges.append(ExposureEdge(
                edge_id=_edge_id(candidate_node, instrument_node, relation, leg.leg_id),
                source_node_id=candidate_node,
                target_node_id=instrument_node,
                relation=relation,
                instrument_id=leg.instrument_id,
                signed_contract_quantity=leg.signed_contract_quantity_per_candidate_unit,
                expiration=leg.expiration,
            ))
            if leg.expiration is not None:
                expiration_node = add_node(ExposureNodeType.EXPIRATION, leg.expiration)
                relation = ExposureRelationType.INSTRUMENT_EXPIRATION
                edges.append(ExposureEdge(
                    edge_id=_edge_id(instrument_node, expiration_node, relation),
                    source_node_id=instrument_node,
                    target_node_id=expiration_node,
                    relation=relation,
                    instrument_id=leg.instrument_id,
                    expiration=leg.expiration,
                ))

    candidates = list(m01.normalized_intents.candidates)
    for left_index, left in enumerate(candidates):
        left_instruments = {leg.instrument_id: leg for leg in left.legs}
        left_expirations = {leg.expiration for leg in left.legs if leg.expiration is not None}
        left_scope = set(groups[left.comparison_group_id].underlying_scope)
        for right in candidates[left_index + 1:]:
            right_instruments = {leg.instrument_id: leg for leg in right.legs}
            right_expirations = {leg.expiration for leg in right.legs if leg.expiration is not None}
            right_scope = set(groups[right.comparison_group_id].underlying_scope)
            source = _node_id(ExposureNodeType.CANDIDATE, left.candidate_id)
            target = _node_id(ExposureNodeType.CANDIDATE, right.candidate_id)
            for instrument_id in sorted(set(left_instruments) & set(right_instruments)):
                relation = ExposureRelationType.SAME_INSTRUMENT
                edges.append(ExposureEdge(
                    edge_id=_edge_id(source, target, relation, instrument_id),
                    source_node_id=source,
                    target_node_id=target,
                    relation=relation,
                    instrument_id=instrument_id,
                ))
                if left_instruments[instrument_id].signed_contract_quantity_per_candidate_unit * right_instruments[instrument_id].signed_contract_quantity_per_candidate_unit < 0:
                    relation = ExposureRelationType.OPPOSITE_LEG
                    edges.append(ExposureEdge(
                        edge_id=_edge_id(source, target, relation, instrument_id),
                        source_node_id=source,
                        target_node_id=target,
                        relation=relation,
                        instrument_id=instrument_id,
                    ))
            for expiration in sorted(left_expirations & right_expirations):
                relation = ExposureRelationType.SAME_EXPIRATION
                edges.append(ExposureEdge(
                    edge_id=_edge_id(source, target, relation, expiration),
                    source_node_id=source,
                    target_node_id=target,
                    relation=relation,
                    expiration=expiration,
                ))
            for underlying in sorted(left_scope & right_scope):
                relation = ExposureRelationType.SAME_UNDERLYING_SCOPE
                edges.append(ExposureEdge(
                    edge_id=_edge_id(source, target, relation, underlying),
                    source_node_id=source,
                    target_node_id=target,
                    relation=relation,
                ))
            if left.objective_family == right.objective_family:
                relation = ExposureRelationType.SAME_OBJECTIVE_FAMILY
                edges.append(ExposureEdge(
                    edge_id=_edge_id(source, target, relation),
                    source_node_id=source,
                    target_node_id=target,
                    relation=relation,
                ))

    nodes = tuple(sorted(node_map.values(), key=lambda item: item.node_id))
    edge_by_id: dict[str, ExposureEdge] = {}
    for edge in edges:
        prior = edge_by_id.get(edge.edge_id)
        if prior is not None and prior != edge:
            raise GraphIntegrityError(f"edge ID collision with different semantics: {edge.edge_id}")
        edge_by_id[edge.edge_id] = edge
    edge_tuple = tuple(edge_by_id[key] for key in sorted(edge_by_id))
    provisional = StructuralExposureGraph(
        contract_version="P8_STRUCTURAL_EXPOSURE_GRAPH_V1",
        schema_version="1.0.0",
        snapshot_id=bundle.snapshot.snapshot_id,
        nodes=nodes,
        edges=edge_tuple,
        connected_components=_components(nodes, edge_tuple),
        content_sha256="0" * 64,
    )
    graph = seal(provisional)
    receipt = build_receipt(
        module_id=MODULE_ID,
        inputs=(m01.normalized_intents, bundle.validated_handoff),
        output=graph,
        computed_at=context.computed_at,
    )
    return M02Result(exposure_graph=graph, receipt=receipt)

run_m02 = run_module
