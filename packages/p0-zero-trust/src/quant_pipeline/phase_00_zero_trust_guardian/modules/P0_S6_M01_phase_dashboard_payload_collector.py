from __future__ import annotations

from typing import Any

from ._p0_s6_core import (
    envelope,
    materialized,
    require_config,
    require_inputs,
    result,
    source_control,
    validate,
)
from ._p0_s6_state import collect_phase_states

REQUIRED = [
    "dashboard_phase_payload_all_phases",
    "phase_test_status_panel",
    "artifact_manifest_audit_report",
]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, set(REQUIRED))
    config = require_config(config)
    container = materialized(inputs[REQUIRED[0]], REQUIRED[0])
    panel = source_control(inputs[REQUIRED[1]], REQUIRED[1])
    audit = source_control(inputs[REQUIRED[2]], REQUIRED[2])
    _validate_runtime_phase_payloads(container)
    phases = collect_phase_states(container, panel)
    blocked = _blocking_sources(panel, audit, phases)
    conflicts = _state_conflicts(container)
    source_lineages = _source_lineages(phases, panel, audit)
    status = "FAIL" if blocked else "PASS"
    payload = {
        "phases": phases,
        "sources": [panel["lineage_id"], audit["lineage_id"]],
        "conflicts": conflicts,
    }
    artifact = envelope("collected_phase_dashboard_payloads", payload, config)
    artifact.update(
        {
            "phase_count": len(phases),
            "phases": phases,
            "source_lineage_ids": source_lineages,
            "source_freshness": "CONFLICTING" if conflicts else "CURRENT",
            "state_conflicts": conflicts,
            "status": status,
            "blocking_sources": blocked,
            "release_blocking": bool(blocked),
            "promotion_blocked": True,
        }
    )
    validate(artifact, "collected_phase_dashboard_payloads.schema.yaml", "collected_phase_dashboard_payloads")
    return result("P0.S6.M01", "phase_dashboard_payload_collector", REQUIRED, {"collected_phase_dashboard_payloads": artifact})


def _validate_runtime_phase_payloads(container: dict[str, Any]) -> None:
    phases = container.get("phases", [])
    if not isinstance(phases, list):
        raise ValueError("dashboard_phase_payload_all_phases.phases must be a list")
    seen: set[str] = set()
    for index, phase in enumerate(phases):
        item = source_control(phase, f"dashboard_phase_payload_all_phases.phases[{index}]")
        pid = item.get("phase_id")
        if not isinstance(pid, str) or not pid:
            raise ValueError("phase payload must include phase_id")
        if pid in seen:
            raise ValueError(f"duplicate phase payload: {pid}")
        seen.add(pid)


def _blocking_sources(panel: dict[str, Any], audit: dict[str, Any], phases: list[dict[str, Any]]) -> list[str]:
    blocked: list[str] = []
    if panel["release_blocking"]:
        blocked.append("phase_test_status_panel")
    if audit["release_blocking"]:
        blocked.append("artifact_manifest_audit_report")
    blocked.extend(phase["phase_id"] for phase in phases if phase["health_status"] == "CRITICAL")
    return sorted(set(blocked))


def _source_lineages(phases: list[dict[str, Any]], panel: dict[str, Any], audit: dict[str, Any]) -> list[str]:
    values = [panel["lineage_id"], audit["lineage_id"]]
    for phase in phases:
        values.extend(phase["source_lineage_ids"])
    return list(dict.fromkeys(values))


def _state_conflicts(container: dict[str, Any]) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    runtime = {x.get("phase_id"): x for x in container.get("phases", []) if isinstance(x, dict)}
    qualification = container.get("qualification_state_snapshot", {})
    records = qualification.get("phases", qualification) if isinstance(qualification, dict) else {}
    if not isinstance(records, dict):
        return conflicts
    for pid, qstate in records.items():
        current = runtime.get(pid)
        if not isinstance(current, dict) or not isinstance(qstate, dict):
            continue
        left = str(current.get("qualification_status", ""))
        right = str(qstate.get("qualification_status", ""))
        if left and right and left != right:
            conflicts.append({"phase_id": str(pid), "runtime": left, "canonical": right})
    return conflicts
