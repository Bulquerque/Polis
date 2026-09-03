from __future__ import annotations

from ._module_executor import ContractValidationError
from ..core import deterministic_id, reject_forbidden_fields, stable_digest


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["source_capture_plan"]
    if "source_capture_plan" not in inputs:
        raise ContractValidationError("missing required inputs: ['source_capture_plan']")
    reject_forbidden_fields(inputs)
    plan = inputs["source_capture_plan"]
    if isinstance(plan, dict) and isinstance(plan.get("tasks"), list):
        tasks = plan["tasks"]
    elif isinstance(plan, dict) and plan.get("source"):
        raise ContractValidationError("source capture plan cannot be synthesized from source")
    elif isinstance(plan, list):
        tasks = plan
    else:
        raise ContractValidationError("source_capture_plan must contain tasks")

    normalized = []
    seen = set()
    for index, raw_task in enumerate(tasks):
        if not isinstance(raw_task, dict) or not raw_task.get("source_id") or not raw_task.get("lineage_id"):
            raise ContractValidationError("every capture task requires source_id and lineage_id")
        task = dict(raw_task)
        task.setdefault("task_id", deterministic_id("task", task.get("run_id"), task["source_id"], index))
        if task["task_id"] in seen:
            raise ContractValidationError("task_id must be unique")
        seen.add(task["task_id"])
        task.setdefault("run_id", plan.get("run_id") if isinstance(plan, dict) else None)
        task.setdefault("contract_mode", plan.get("contract_mode", "LEGACY_V1") if isinstance(plan, dict) else "LEGACY_V1")
        task.setdefault("dataset_id", task.get("dataset") or task["source_id"])
        task.setdefault("dataset", task["dataset_id"])
        task.setdefault("partition_id", "default")
        task.setdefault("provider", task["source_id"])
        task.setdefault("adapter_id", "generic_http")
        task.setdefault("capture_state", "PLANNED")
        task.setdefault("attempt_count", 0)
        task.setdefault("capture_ids", [])
        normalized.append(task)

    normalized.sort(key=lambda row: (
        str(row.get("source_id", "")), str(row.get("dataset_id", "")),
        str(row.get("partition_id", "")), str(row.get("task_id", "")),
    ))
    digest = stable_digest({"tasks": normalized, "run_id": plan.get("run_id") if isinstance(plan, dict) else None})
    return {
        "module_id": "P1.S2.M01",
        "module_name": "source_capture_orchestrator",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S2",
        "contract": "P1_S2_M01_source_capture_orchestrator.yaml",
        "required_inputs": required,
        "outputs": {"capture_task_manifest": {
            "artifact_id": f"capture_task_manifest-{digest[:12]}",
            "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
            "lineage_id": f"lineage-capture-task-manifest-{digest[:12]}",
            "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
            "schema_version": "2",
            "run_id": plan.get("run_id") if isinstance(plan, dict) else None,
            "as_of_time": plan.get("as_of_time") if isinstance(plan, dict) else None,
            "contract_mode": plan.get("contract_mode", "LEGACY_V1") if isinstance(plan, dict) else "LEGACY_V1",
            "tasks": normalized,
            "task_count": len(normalized),
        }},
    }
