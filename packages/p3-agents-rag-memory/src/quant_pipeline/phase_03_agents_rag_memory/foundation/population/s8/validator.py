"""P3.S8.M02 relationship-prior validator. It never repairs the graph."""
from __future__ import annotations

from collections import defaultdict
import json
import math

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
    CheckStatus,
    GraphMetrics,
    IssueSeverity,
    RelationshipPriorValidationRequest,
    RelationshipPriorValidationResult,
    ValidationCheck,
    ValidationIssue,
    ValidationStatus,
    ValidatedInitialSocialGraph,
)


class RelationshipPriorValidator:
    """Validate topology, reciprocity, relation semantics and trust bounds."""

    module_id = "P3.S8.M02"

    def execute(self, request: RelationshipPriorValidationRequest) -> RelationshipPriorValidationResult:
        graph = request.initial_social_graph
        config = request.social_graph_config
        issues: list[ValidationIssue] = []
        checks: list[ValidationCheck] = []
        nodes = {node.person_id: node for node in graph.nodes}
        config_hash = sha256_hex(config.model_dump(mode="json"), float_digits=config.numeric_precision)
        if graph.config_hash != config_hash:
            self._issue(issues, "CONFIG_HASH_MISMATCH", graph.graph_id)
        if set(graph.relationship_type_registry) != set(config.relationship_types):
            self._issue(issues, "RELATIONSHIP_REGISTRY_MISMATCH", graph.graph_id)
        if set(graph.trust_domain_registry) != set(config.trust_domains):
            self._issue(issues, "TRUST_REGISTRY_MISMATCH", graph.graph_id)
        expected_seed = stable_uint63({
            "algorithm": config.graph_seed_algorithm,
            "population_id": graph.population_id,
            "validated_population_manifest_hash": graph.validated_population_manifest_hash,
            "person_seed_panel_hash": graph.person_seed_panel_hash,
            "config_hash": config_hash,
            "contract": "P3.S8.v2",
        }, float_digits=config.numeric_precision)
        if graph.graph_seed != expected_seed:
            self._issue(issues, "GRAPH_SEED_MISMATCH", graph.graph_id)
        for node in graph.nodes:
            node_base = {
                "person_id": node.person_id,
                "candidate_id": node.candidate_id,
                "representation_weight": node.representation_weight,
                "person_seed": node.person_seed,
                "economic_role": node.economic_role,
                "role_family": node.role_family,
                "institution_type": node.institution_type,
                "geography": node.geography,
                "tags": [item.model_dump(mode="json") for item in node.tags],
                "capabilities": node.capabilities.model_dump(mode="json"),
                "resources": node.resources.model_dump(mode="json"),
                "profile_fingerprint": node.profile_fingerprint,
            }
            if sha256_hex(node_base) != node.node_hash:
                self._issue(issues, "NODE_HASH_MISMATCH", node.person_id)
        edge_ids = set()
        directed_pairs = set()
        edges_by_pair = defaultdict(list)
        for edge in graph.edges:
            if edge.edge_id in edge_ids:
                self._issue(issues, "DUPLICATE_EDGE_ID", edge.edge_id)
            edge_ids.add(edge.edge_id)
            key = (edge.source_person_id, edge.target_person_id)
            if key in directed_pairs:
                self._issue(issues, "DUPLICATE_DIRECTED_EDGE", *key)
            directed_pairs.add(key)
            if edge.source_person_id not in nodes or edge.target_person_id not in nodes:
                self._issue(issues, "UNKNOWN_EDGE_NODE", edge.edge_id)
                continue
            edges_by_pair[edge.reciprocal_pair_id].append(edge)
            expected_type = relationship_type(nodes[edge.source_person_id], nodes[edge.target_person_id])
            if edge.relationship_type != expected_type:
                self._issue(issues, "RELATIONSHIP_TYPE_SEMANTIC_MISMATCH", edge.edge_id)
            if edge.relationship_type not in config.relationship_types:
                self._issue(issues, "UNKNOWN_RELATIONSHIP_TYPE", edge.edge_id)
            domains = {item.domain_id for item in edge.domain_trust}
            if domains != set(config.trust_domains):
                self._issue(issues, "TRUST_DOMAIN_SET_MISMATCH", edge.edge_id)
            if not config.global_trust_floor <= edge.global_trust <= config.global_trust_ceiling:
                self._issue(issues, "GLOBAL_TRUST_OUT_OF_CONFIG_RANGE", edge.edge_id)
            if edge.source_person_id == edge.target_person_id:
                self._issue(issues, "SELF_LOOP_FORBIDDEN", edge.edge_id)
            source = nodes[edge.source_person_id]
            target = nodes[edge.target_person_id]
            pair = canonical_pair(source.person_id, target.person_id)
            expected_probability = pair_probability(source, target, config)
            expected_uniform = stable_unit_interval({
                "algorithm": config.pair_random_algorithm,
                "graph_seed": graph.graph_seed,
                "pair": pair,
            })
            if abs(edge.selection_probability - expected_probability) > 1e-12:
                self._issue(issues, "EDGE_PROBABILITY_MISMATCH", edge.edge_id)
            if abs(edge.pair_uniform - expected_uniform) > 1e-12:
                self._issue(issues, "PAIR_UNIFORM_MISMATCH", edge.edge_id)
            expected_domains = domain_trust(source, target, config)
            actual_domains = {item.domain_id: item.value for item in edge.domain_trust}
            if any(abs(actual_domains.get(domain, -1.0) - value) > 1e-12 for domain, value in expected_domains.items()):
                self._issue(issues, "DOMAIN_TRUST_MISMATCH", edge.edge_id)
            expected_global = global_trust(source, target, expected_domains, config)
            if abs(edge.global_trust - expected_global) > 1e-12:
                self._issue(issues, "GLOBAL_TRUST_MISMATCH", edge.edge_id)
            if abs(edge.influence - influence(source, target)) > 1e-12:
                self._issue(issues, "INFLUENCE_MISMATCH", edge.edge_id)
            if abs(edge.interaction_frequency - interaction_frequency(source, target)) > 1e-12:
                self._issue(issues, "INTERACTION_FREQUENCY_MISMATCH", edge.edge_id)
            expected_edge_hash = sha256_hex({
                "graph_id": graph.graph_id,
                "pair_id": edge.reciprocal_pair_id,
                "source": edge.source_person_id,
                "target": edge.target_person_id,
                "relationship_type": edge.relationship_type,
                "origin": edge.origin.value,
                "global_trust": edge.global_trust,
                "domain_trust": [item.model_dump(mode="json") for item in edge.domain_trust],
                "influence": edge.influence,
                "interaction_frequency": edge.interaction_frequency,
                "selection_probability": edge.selection_probability,
                "pair_uniform": edge.pair_uniform,
            }, float_digits=config.numeric_precision)
            if expected_edge_hash != edge.edge_hash:
                self._issue(issues, "EDGE_HASH_MISMATCH", edge.edge_id)
            expected_edge_id = stable_id("edge", {"algorithm": config.edge_id_algorithm, "edge_hash": expected_edge_hash})
            if edge.edge_id != expected_edge_id:
                self._issue(issues, "EDGE_ID_MISMATCH", edge.edge_id)
        for pair_id, pair_edges in sorted(edges_by_pair.items()):
            if len(pair_edges) != 2:
                self._issue(issues, "RECIPROCAL_PAIR_CARDINALITY_INVALID", pair_id)
                continue
            first, second = pair_edges
            if not (
                first.source_person_id == second.target_person_id
                and first.target_person_id == second.source_person_id
            ):
                self._issue(issues, "RECIPROCAL_PAIR_DIRECTION_INVALID", pair_id)
            if first.relationship_type != second.relationship_type or first.origin != second.origin:
                self._issue(issues, "RECIPROCAL_PAIR_SEMANTICS_INVALID", pair_id)
        pair_values = {
            canonical_pair(edge.source_person_id, edge.target_person_id)
            for edge in graph.edges
            if edge.source_person_id in nodes and edge.target_person_id in nodes
        }
        degree_map = degrees(nodes, pair_values)
        components = connected_components(nodes, pair_values)
        bridge_count = sum(1 for left, right in pair_values if nodes[left].role_family != nodes[right].role_family)
        metric = self._metrics(graph, nodes, pair_values, degree_map, components, bridge_count)
        self._check(checks, issues, "node_set", set(nodes) == set(graph.metrics.degree_by_person), len(nodes), graph.metrics.node_count)
        self._check(checks, issues, "reciprocal_pairs", all(len(values) == 2 for values in edges_by_pair.values()), len(edges_by_pair), graph.metrics.reciprocal_pair_count)
        self._check(checks, issues, "minimum_degree", min(degree_map.values()) >= config.minimum_neighbor_degree, min(degree_map.values()), config.minimum_neighbor_degree)
        self._check(checks, issues, "maximum_degree", max(degree_map.values()) <= config.maximum_neighbor_degree, max(degree_map.values()), config.maximum_neighbor_degree)
        self._check(checks, issues, "components", len(components) <= config.maximum_connected_components, len(components), config.maximum_connected_components)
        self._check(checks, issues, "isolates", all(value > 0 for value in degree_map.values()), sum(value == 0 for value in degree_map.values()), 0)
        self._check(checks, issues, "bridge_quota", bridge_count >= config.minimum_bridge_pairs_between_role_families, bridge_count, config.minimum_bridge_pairs_between_role_families)
        self._check(checks, issues, "hub_share", hub_share(degree_map) <= config.maximum_hub_share, hub_share(degree_map), config.maximum_hub_share)
        if metric.model_dump(mode="json") != graph.metrics.model_dump(mode="json"):
            self._issue(issues, "GRAPH_METRICS_MISMATCH", graph.graph_id)
        pair_origins = {}
        for pair_id, pair_edges in edges_by_pair.items():
            if pair_edges:
                pair = canonical_pair(pair_edges[0].source_person_id, pair_edges[0].target_person_id)
                pair_origins[pair] = pair_edges[0].origin.value
        expected_graph_id = stable_id("graph", {
            "population_id": graph.population_id,
            "graph_seed": graph.graph_seed,
            "pairs": sorted((left, right, origin) for (left, right), origin in pair_origins.items()),
            "config_hash": config_hash,
        })
        if graph.graph_id != expected_graph_id:
            self._issue(issues, "GRAPH_ID_MISMATCH", graph.graph_id)
        payload = {
            "creator_run_id": graph.creator_run_id,
            "population_id": graph.population_id,
            "graph_id": graph.graph_id,
            "graph_seed": graph.graph_seed,
            "graph_direction": graph.graph_direction.value,
            "nodes": [node.model_dump(mode="json") for node in graph.nodes],
            "edges": [edge.model_dump(mode="json") for edge in graph.edges],
            "metrics": graph.metrics.model_dump(mode="json"),
            "relationship_type_registry": list(graph.relationship_type_registry),
            "trust_domain_registry": list(graph.trust_domain_registry),
            "population_manifest_hash": graph.population_manifest_hash,
            "validated_population_manifest_hash": graph.validated_population_manifest_hash,
            "person_seed_panel_hash": graph.person_seed_panel_hash,
            "config_hash": graph.config_hash,
        }
        if sha256_hex(payload, float_digits=config.numeric_precision) != graph.graph_hash:
            self._issue(issues, "GRAPH_HASH_MISMATCH", graph.graph_id)
        status = ValidationStatus.BLOCKED if any(item.severity is IssueSeverity.ERROR for item in issues) else ValidationStatus.READY
        content = {
            "graph_hash": graph.graph_hash,
            "status": status.value,
            "checks": [item.model_dump(mode="json") for item in checks],
            "issues": [item.model_dump(mode="json") for item in issues],
        }
        validated_hash = sha256_hex(content)
        validated = ValidatedInitialSocialGraph(
            validation_status=status,
            initial_social_graph=graph,
            checks=tuple(checks),
            issues=tuple(issues),
            validated_graph_hash=validated_hash,
            lineage_id=stable_id("lin", {"module": self.module_id, "validated_hash": validated_hash}),
        )
        return RelationshipPriorValidationResult(validated_initial_social_graph=validated)

    def _metrics(self, graph, nodes, pairs, degree_map, components, bridge_count) -> GraphMetrics:
        seen = set()
        relations = []
        for edge in graph.edges:
            if edge.reciprocal_pair_id not in seen:
                seen.add(edge.reciprocal_pair_id)
                relations.append(edge.relationship_type)
        family_pairs = ["::".join(sorted((nodes[left].role_family, nodes[right].role_family))) for left, right in pairs]
        return GraphMetrics(
            node_count=len(nodes),
            directed_edge_count=len(graph.edges),
            reciprocal_pair_count=len(pairs),
            connected_component_count=len(components),
            isolated_node_count=sum(1 for value in degree_map.values() if value == 0),
            cross_family_bridge_pair_count=bridge_count,
            minimum_neighbor_degree=min(degree_map.values()),
            maximum_neighbor_degree=max(degree_map.values()),
            mean_neighbor_degree=math.fsum(degree_map.values()) / len(degree_map),
            maximum_hub_share=hub_share(degree_map),
            degree_by_person=dict(sorted(degree_map.items())),
            relationship_pair_counts=pair_counts(relations),
            role_family_pair_counts=pair_counts(family_pairs),
        )

    def _issue(self, issues, code: str, *subjects: str) -> None:
        issues.append(ValidationIssue(issue_code=code, severity=IssueSeverity.ERROR, message=code.replace("_", " ").title(), subject_ids=tuple(subjects)))

    def _check(self, checks, issues, check_id: str, passed: bool, observed, expected) -> None:
        code = f"{check_id.upper()}_FAILED"
        checks.append(ValidationCheck(
            check_id=check_id,
            status=CheckStatus.PASS if passed else CheckStatus.FAIL,
            observed=json.dumps(observed, sort_keys=True),
            expected=json.dumps(expected, sort_keys=True),
            issue_codes=() if passed else (code,),
        ))
        if not passed:
            self._issue(issues, code)
