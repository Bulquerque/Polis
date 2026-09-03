from __future__ import annotations


def strong_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph.get(node, set())):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indices[target])
        if low[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1 or node in graph.get(node, set()):
            components.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components)


def runtime_lineage(records, module_ids: set[str]):
    explicit = [record for record in records if record.producer_module_id or record.parents]
    if not explicit:
        return [], [], False
    by_identity = {record.artifact_id: record for record in records}
    duplicate_ids = len(by_identity) != len(records)
    graph = {record.artifact_id: set(record.parents) for record in explicit}
    checks = []
    for record in explicit:
        codes: list[str] = []
        if duplicate_ids and sum(item.artifact_id == record.artifact_id for item in records) > 1:
            codes.append("DUPLICATE_ARTIFACT_ID")
        if record.producer_module_id and record.producer_module_id not in module_ids:
            codes.append("UNKNOWN_PRODUCER_MODULE")
        if any(parent not in by_identity for parent in record.parents):
            codes.append("MISSING_PARENT_ARTIFACT")
        checks.append(
            {
                "artifact_id": record.artifact_id,
                "producer_module_id": record.producer_module_id,
                "parent_count": len(record.parents),
                "status": "FAIL" if codes else "PASS",
                "codes": sorted(set(codes)) or ["PASS"],
            }
        )
    cycles = strong_components({node: {parent for parent in parents if parent in graph} for node, parents in graph.items()})
    cycle_nodes = {node for component in cycles for node in component}
    for check in checks:
        if check["artifact_id"] in cycle_nodes:
            check["status"] = "FAIL"
            check["codes"] = sorted(set(check["codes"] + ["RUNTIME_LINEAGE_CYCLE"]))
    return checks, cycles, True
