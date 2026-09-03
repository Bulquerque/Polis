from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

import yaml

from quant_pipeline.phase_03_agents_rag_memory.orchestration.registry import (
    EXECUTABLE_MODULE_REGISTRY,
    MODULE_REGISTRY,
    by_id,
)

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str):
    return yaml.safe_load((ROOT / "config/research_tools" / name).read_text())


def test_unified_counts_and_unique_authorities() -> None:
    modules = _load("MODULE_REGISTRY_S32_S40.yaml")
    handlers = _load("HANDLER_REGISTRY_S32_S40.yaml")
    schemas = _load("SCHEMA_BINDINGS_S32_S40.yaml")
    assert modules["subphase_count"] == 9
    assert modules["module_count"] == 47
    assert modules["legacy_module_count_preserved"] == 81
    assert handlers["operation_count"] == 34
    assert schemas["binding_count"] == 34
    assert len({item["module_id"] for item in modules["modules"]}) == 47
    assert len({(item["tool_id"], item["operation_id"]) for item in handlers["operations"]}) == 34


def test_legacy_authority_is_stable_while_executor_discovers_extension() -> None:
    assert len(MODULE_REGISTRY) == 81
    assert len(EXECUTABLE_MODULE_REGISTRY) == 128
    assert by_id("P3.S40.M08").module_name == "research_tool_extension_release_gate"


def test_all_declared_files_and_schemas_exist() -> None:
    modules = _load("MODULE_REGISTRY_S32_S40.yaml")
    for item in modules["modules"]:
        assert (ROOT / item["contract_path"]).is_file()
        assert (ROOT / item["implementation_path"]).is_file()
    schemas = _load("SCHEMA_BINDINGS_S32_S40.yaml")
    for item in schemas["bindings"]:
        assert (ROOT / item["request_schema_path"]).is_file()
        assert (ROOT / item["result_schema_path"]).is_file()


def test_extension_dag_is_acyclic_and_references_known_nodes() -> None:
    dag = _load("RESEARCH_TOOL_EXTENSION_DAG_S32_S40.yaml")
    nodes = set(dag["nodes"])
    graph: dict[str, set[str]] = defaultdict(set)
    indegree = {node: 0 for node in nodes}
    for edge in dag["edges"]:
        assert edge["from"] in nodes
        assert edge["to"] in nodes
        assert edge["artifacts"]
        if edge["to"] not in graph[edge["from"]]:
            graph[edge["from"]].add(edge["to"])
            indegree[edge["to"]] += 1
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for target in sorted(graph[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    assert visited == len(nodes)
    external_pairs = {
        (edge["from"], edge["to"])
        for edge in dag.get("external_connections", ())
    }
    assert ("P3.S40.M06", "P4") not in external_pairs
    assert ("P3.S40.M07", "P9") not in external_pairs
    deferred = {item["from"]: item for item in dag["deferred_consumer_candidates"]}
    assert deferred["P3.S40.M07"]["status"] == "DEFERRED_BY_GOVERNANCE"


def test_no_duplicate_agent2_wrappers_or_transient_artifacts() -> None:
    legacy = ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/modules"
    extension = ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/modules"
    assert len(list(legacy.glob("P3_S*_M*.py"))) == 81
    assert len(list(extension.glob("P3_S*_M*.py"))) == 47
    assert not list(legacy.glob("P3_S3[2-9]_M*.py"))
    assert not list(legacy.glob("P3_S40_M*.py"))
