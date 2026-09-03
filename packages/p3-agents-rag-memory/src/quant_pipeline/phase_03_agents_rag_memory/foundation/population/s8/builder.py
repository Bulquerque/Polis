"""P3.S8.M01 deterministic initial social graph builder."""
from __future__ import annotations

from collections import defaultdict
import math

from .errors import ContractError, GraphConstructionError
from .graph_algorithms import canonical_pair, connected_components, degrees, hub_share, pair_counts
from .graph_math import (
    domain_trust,
    global_trust,
    influence,
    interaction_frequency,
    pair_probability,
    relationship_type,
)
from .hashing import sha256_hex, stable_id, stable_uint63, stable_unit_interval
from .models import (
    CapabilityVector,
    DomainTrust,
    EdgeOrigin,
    GraphDirection,
    GraphMetrics,
    InitialSocialGraph,
    InitialSocialGraphBuildRequest,
    InitialSocialGraphBuildResult,
    ResourceVector,
    SocialEdge,
    SocialNode,
    TagValue,
)


class InitialSocialGraphBuilder:
    """Build reciprocal directed edges from a deterministic undirected pair skeleton."""

    module_id = "P3.S8.M01"

    def execute(self, request: InitialSocialGraphBuildRequest) -> InitialSocialGraphBuildResult:
        config = request.social_graph_config
        manifest = request.validated_population_manifest
        panel = request.person_seed_panel
        self._validate_upstream(manifest, panel, request.personality_tag_registry)
        nodes = self._nodes(manifest.population_manifest.persons, request.personality_tag_registry)
        config_hash = sha256_hex(config.model_dump(mode="json"), float_digits=config.numeric_precision)
        graph_seed = stable_uint63(
            {
                "algorithm": config.graph_seed_algorithm,
                "population_id": manifest.population_manifest.population_id,
                "validated_population_manifest_hash": manifest.validated_manifest_hash,
                "person_seed_panel_hash": panel.panel_hash,
                "config_hash": config_hash,
                "contract": "P3.S8.v2",
            },
            float_digits=config.numeric_precision,
        )
        selected: dict[tuple[str, str], EdgeOrigin] = {}
        degree_map = {node.person_id: 0 for node in nodes}
        node_by_id = {node.person_id: node for node in nodes}
        families: dict[str, list[SocialNode]] = defaultdict(list)
        for node in nodes:
            families[node.role_family].append(node)
        for values in families.values():
            values.sort(key=lambda item: item.person_id)

        # Intra-family cycle/chain: low-hub backbone with deterministic ordering.
        for family in sorted(families):
            members = families[family]
            if len(members) == 2:
                self._add_pair(selected, degree_map, members[0], members[1], EdgeOrigin.INTRA_FAMILY_BACKBONE, config)
            elif len(members) > 2:
                for index, left in enumerate(members):
                    right = members[(index + 1) % len(members)]
                    self._add_pair(selected, degree_map, left, right, EdgeOrigin.INTRA_FAMILY_BACKBONE, config)

        # Ring across role families, choosing the strongest feasible pair for each adjacent family.
        family_names = sorted(families)
        if len(family_names) > 1:
            family_links = [
                (family_names[index], family_names[(index + 1) % len(family_names)])
                for index in range(len(family_names))
            ]
            for left_family, right_family in family_links:
                pair = self._best_pair(
                    families[left_family], families[right_family], selected, degree_map, config
                )
                if pair is None:
                    raise GraphConstructionError("P3_S8_M01_CANNOT_CONNECT_ROLE_FAMILY_RING")
                self._add_pair(selected, degree_map, *pair, EdgeOrigin.CROSS_FAMILY_BRIDGE, config)

        # Additional cross-family bridges if quota exceeds the family ring.
        while self._bridge_count(selected, node_by_id) < config.minimum_bridge_pairs_between_role_families:
            pair = self._best_cross_family_pair(nodes, selected, degree_map, config)
            if pair is None:
                raise GraphConstructionError("P3_S8_M01_BRIDGE_QUOTA_IMPOSSIBLE")
            self._add_pair(selected, degree_map, *pair, EdgeOrigin.CROSS_FAMILY_BRIDGE, config)

        # Mandatory minimum degree repair, selecting highest-probability feasible pairs.
        while min(degree_map.values()) < config.minimum_neighbor_degree:
            low = min((node for node in nodes if degree_map[node.person_id] < config.minimum_neighbor_degree), key=lambda item: item.person_id)
            candidates = [
                other for other in nodes
                if other.person_id != low.person_id
                and canonical_pair(low.person_id, other.person_id) not in selected
                and degree_map[other.person_id] < config.maximum_neighbor_degree
            ]
            candidates.sort(key=lambda other: (-pair_probability(low, other, config), other.person_id))
            if not candidates:
                raise GraphConstructionError("P3_S8_M01_MINIMUM_DEGREE_IMPOSSIBLE")
            self._add_pair(selected, degree_map, low, candidates[0], EdgeOrigin.MIN_DEGREE_REPAIR, config)

        # Additional probabilistic pairs, deterministic through pair hashing.
        candidate_pairs = []
        for index, left in enumerate(nodes):
            for right in nodes[index + 1:]:
                pair = canonical_pair(left.person_id, right.person_id)
                if pair in selected:
                    continue
                probability = pair_probability(left, right, config)
                uniform = stable_unit_interval(
                    {"algorithm": config.pair_random_algorithm, "graph_seed": graph_seed, "pair": pair}
                )
                candidate_pairs.append((uniform - probability, pair, left, right, probability, uniform))
        candidate_pairs.sort(key=lambda item: (item[0], item[1]))
        for _, pair, left, right, probability, uniform in candidate_pairs:
            if uniform >= probability:
                continue
            if degree_map[left.person_id] >= config.maximum_neighbor_degree:
                continue
            if degree_map[right.person_id] >= config.maximum_neighbor_degree:
                continue
            self._add_pair(selected, degree_map, left, right, EdgeOrigin.PROBABILISTIC, config)

        graph_id = stable_id(
            "graph",
            {
                "population_id": manifest.population_manifest.population_id,
                "graph_seed": graph_seed,
                "pairs": sorted((left, right, origin.value) for (left, right), origin in selected.items()),
                "config_hash": config_hash,
            },
        )
        edges: list[SocialEdge] = []
        for (left_id, right_id), origin in sorted(selected.items()):
            left = node_by_id[left_id]
            right = node_by_id[right_id]
            probability = pair_probability(left, right, config)
            uniform = stable_unit_interval(
                {"algorithm": config.pair_random_algorithm, "graph_seed": graph_seed, "pair": (left_id, right_id)}
            )
            pair_id = stable_id("pair", {"graph_id": graph_id, "left": left_id, "right": right_id})
            edges.extend([
                self._edge(graph_id, pair_id, left, right, origin, probability, uniform, config),
                self._edge(graph_id, pair_id, right, left, origin, probability, uniform, config),
            ])
        edges_tuple = tuple(sorted(edges, key=lambda edge: edge.edge_id))
        pairs = set(selected)
        metric = self._metrics(nodes, edges_tuple, pairs, node_by_id)
        payload = {
            "creator_run_id": manifest.population_manifest.creator_run_id,
            "population_id": manifest.population_manifest.population_id,
            "graph_id": graph_id,
            "graph_seed": graph_seed,
            "graph_direction": GraphDirection.DIRECTED_RECIPROCAL_PAIRS.value,
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges_tuple],
            "metrics": metric.model_dump(mode="json"),
            "relationship_type_registry": sorted(config.relationship_types),
            "trust_domain_registry": sorted(config.trust_domains),
            "population_manifest_hash": manifest.population_manifest.manifest_hash,
            "validated_population_manifest_hash": manifest.validated_manifest_hash,
            "person_seed_panel_hash": panel.panel_hash,
            "config_hash": config_hash,
        }
        graph_hash = sha256_hex(payload, float_digits=config.numeric_precision)
        graph = InitialSocialGraph(
            creator_run_id=manifest.population_manifest.creator_run_id,
            population_id=manifest.population_manifest.population_id,
            graph_id=graph_id,
            graph_seed=graph_seed,
            graph_direction=GraphDirection.DIRECTED_RECIPROCAL_PAIRS,
            nodes=nodes,
            edges=edges_tuple,
            metrics=metric,
            relationship_type_registry=tuple(sorted(config.relationship_types)),
            trust_domain_registry=tuple(sorted(config.trust_domains)),
            population_manifest_hash=manifest.population_manifest.manifest_hash,
            validated_population_manifest_hash=manifest.validated_manifest_hash,
            person_seed_panel_hash=panel.panel_hash,
            config_hash=config_hash,
            graph_hash=graph_hash,
            lineage_id=stable_id("lin", {"module": self.module_id, "graph_hash": graph_hash}),
        )
        return InitialSocialGraphBuildResult(initial_social_graph=graph)

    def _validate_upstream(self, manifest, panel, tag_registry: tuple[str, ...]) -> None:
        if manifest.validation_status.value != "READY":
            raise ContractError("P3_S8_M01_POPULATION_NOT_READY")
        population = manifest.population_manifest
        if panel.population_id != population.population_id:
            raise ContractError("P3_S8_M01_POPULATION_ID_MISMATCH")
        if panel.creator_run_id != population.creator_run_id:
            raise ContractError("P3_S8_M01_CREATOR_RUN_MISMATCH")
        person_by_id = {person.person_id: person for person in population.persons}
        seed_by_id = {record.person_id: record for record in panel.records}
        if set(person_by_id) != set(seed_by_id):
            raise ContractError("P3_S8_M01_PERSON_SEED_SET_MISMATCH")
        for person_id, person in person_by_id.items():
            record = seed_by_id[person_id]
            if record.person_seed != person.person_seed or record.candidate_id != person.candidate_id:
                raise ContractError(f"P3_S8_M01_PERSON_SEED_BINDING_MISMATCH:{person_id}")
        known = set(tag_registry)
        actual = {tag.tag_id for person in population.persons for tag in person.profile.tags}
        unknown = actual - known
        if unknown:
            raise ContractError(f"P3_S8_M01_UNKNOWN_TAGS:{','.join(sorted(unknown))}")

    def _nodes(self, persons, tag_registry: tuple[str, ...]) -> tuple[SocialNode, ...]:
        del tag_registry
        nodes = []
        for person in sorted(persons, key=lambda item: item.person_id):
            tags = tuple(sorted(
                (TagValue(tag_id=item.tag_id, effective_value=item.intensity * item.confidence) for item in person.profile.tags),
                key=lambda item: item.tag_id,
            ))
            base = {
                "person_id": person.person_id,
                "candidate_id": person.candidate_id,
                "representation_weight": person.representation_weight,
                "person_seed": person.person_seed,
                "economic_role": person.profile.economic_role,
                "role_family": person.profile.role_family,
                "institution_type": person.profile.institution_type,
                "geography": person.profile.geography,
                "tags": [item.model_dump(mode="json") for item in tags],
                "capabilities": person.profile.capabilities.model_dump(mode="json"),
                "resources": {
                    "information_access": person.profile.resources.information_access,
                    "research_time": person.profile.resources.research_time,
                    "computational_access": person.profile.resources.computational_access,
                },
                "profile_fingerprint": person.profile_fingerprint,
            }
            node_hash = sha256_hex(base)
            nodes.append(SocialNode(
                **base,
                node_hash=node_hash,
                lineage_id=stable_id("lin", {"module": self.module_id, "node_hash": node_hash}),
            ))
        return tuple(nodes)

    def _add_pair(self, selected, degree_map, left, right, origin, config) -> None:
        pair = canonical_pair(left.person_id, right.person_id)
        if pair in selected:
            return
        if degree_map[left.person_id] >= config.maximum_neighbor_degree:
            raise GraphConstructionError(f"P3_S8_M01_MAX_DEGREE_BLOCKED:{left.person_id}")
        if degree_map[right.person_id] >= config.maximum_neighbor_degree:
            raise GraphConstructionError(f"P3_S8_M01_MAX_DEGREE_BLOCKED:{right.person_id}")
        selected[pair] = origin
        degree_map[left.person_id] += 1
        degree_map[right.person_id] += 1

    def _best_pair(self, left_nodes, right_nodes, selected, degree_map, config):
        candidates = []
        for left in left_nodes:
            for right in right_nodes:
                pair = canonical_pair(left.person_id, right.person_id)
                if pair in selected:
                    continue
                if degree_map[left.person_id] >= config.maximum_neighbor_degree:
                    continue
                if degree_map[right.person_id] >= config.maximum_neighbor_degree:
                    continue
                candidates.append((-pair_probability(left, right, config), pair, left, right))
        return None if not candidates else min(candidates)[2:]

    def _best_cross_family_pair(self, nodes, selected, degree_map, config):
        candidates = []
        for index, left in enumerate(nodes):
            for right in nodes[index + 1:]:
                if left.role_family == right.role_family:
                    continue
                pair = canonical_pair(left.person_id, right.person_id)
                if pair in selected:
                    continue
                if degree_map[left.person_id] >= config.maximum_neighbor_degree:
                    continue
                if degree_map[right.person_id] >= config.maximum_neighbor_degree:
                    continue
                candidates.append((-pair_probability(left, right, config), pair, left, right))
        return None if not candidates else min(candidates)[2:]

    def _bridge_count(self, selected, node_by_id) -> int:
        return sum(1 for left, right in selected if node_by_id[left].role_family != node_by_id[right].role_family)

    def _edge(self, graph_id, pair_id, source, target, origin, probability, uniform, config) -> SocialEdge:
        trust_map = domain_trust(source, target, config)
        trust_entries = tuple(DomainTrust(domain_id=domain, value=value) for domain, value in sorted(trust_map.items()))
        edge_base = {
            "graph_id": graph_id,
            "pair_id": pair_id,
            "source": source.person_id,
            "target": target.person_id,
            "relationship_type": relationship_type(source, target),
            "origin": origin.value,
            "global_trust": global_trust(source, target, trust_map, config),
            "domain_trust": [entry.model_dump(mode="json") for entry in trust_entries],
            "influence": influence(source, target),
            "interaction_frequency": interaction_frequency(source, target),
            "selection_probability": probability,
            "pair_uniform": uniform,
        }
        edge_hash = sha256_hex(edge_base, float_digits=config.numeric_precision)
        return SocialEdge(
            edge_id=stable_id("edge", {"algorithm": config.edge_id_algorithm, "edge_hash": edge_hash}),
            reciprocal_pair_id=pair_id,
            source_person_id=source.person_id,
            target_person_id=target.person_id,
            relationship_type=edge_base["relationship_type"],
            origin=origin,
            global_trust=edge_base["global_trust"],
            domain_trust=trust_entries,
            influence=edge_base["influence"],
            interaction_frequency=edge_base["interaction_frequency"],
            selection_probability=probability,
            pair_uniform=uniform,
            edge_hash=edge_hash,
            lineage_id=stable_id("lin", {"module": self.module_id, "edge_hash": edge_hash}),
        )

    def _metrics(self, nodes, edges, pairs, node_by_id) -> GraphMetrics:
        node_ids = [node.person_id for node in nodes]
        degree_map = degrees(node_ids, pairs)
        components = connected_components(node_ids, pairs)
        relation_by_pair = []
        seen = set()
        for edge in edges:
            if edge.reciprocal_pair_id in seen:
                continue
            seen.add(edge.reciprocal_pair_id)
            relation_by_pair.append(edge.relationship_type)
        family_pairs = [
            "::".join(sorted((node_by_id[left].role_family, node_by_id[right].role_family)))
            for left, right in pairs
        ]
        return GraphMetrics(
            node_count=len(nodes),
            directed_edge_count=len(edges),
            reciprocal_pair_count=len(pairs),
            connected_component_count=len(components),
            isolated_node_count=sum(1 for value in degree_map.values() if value == 0),
            cross_family_bridge_pair_count=self._bridge_count({pair: EdgeOrigin.CROSS_FAMILY_BRIDGE for pair in pairs}, node_by_id),
            minimum_neighbor_degree=min(degree_map.values()),
            maximum_neighbor_degree=max(degree_map.values()),
            mean_neighbor_degree=math.fsum(degree_map.values()) / len(degree_map),
            maximum_hub_share=hub_share(degree_map),
            degree_by_person=degree_map,
            relationship_pair_counts=pair_counts(relation_by_pair),
            role_family_pair_counts=pair_counts(family_pairs),
        )
