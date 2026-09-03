from __future__ import annotations

from typing import Any

from ._p0_s6_core import envelope, require_config, require_inputs, result, source_control, source_summary, validate
from ._p0_s6_state import aggregate_counts

REQUIRED = [
    "collected_phase_dashboard_payloads",
    "global_test_report",
    "code_quality_report",
    "hash_integrity_report",
]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, set(REQUIRED))
    config = require_config(config)
    collected = _collected(inputs[REQUIRED[0]])
    reports = {name: source_control(inputs[name], name) for name in REQUIRED[1:]}
    phases = [_resolve_phase_health(phase, reports) for phase in collected["phases"]]
    critical = _critical_errors(phases, reports)
    warnings = _warnings(phases, collected, reports)
    readiness = "READY" if phases and all(p["readiness"] == "READY" for p in phases) and not critical else "NOT_READY"
    health = _overall_health(phases, critical, warnings)
    validation_blocking = bool(critical) or collected.get("release_blocking") is True
    release_blocking = validation_blocking
    status = "FAIL" if validation_blocking else "PASS"
    sources = [source_summary(collected, REQUIRED[0])] + [source_summary(reports[name], name) for name in REQUIRED[1:]]
    development_summary = aggregate_counts(phases)
    artifact = envelope("phase_health_panel", {"phases": phases, "sources": sources}, config)
    artifact.update(
        {
            "phase_count": len(phases),
            "phases": phases,
            "phase_statuses": phases,
            "source_reports": sources,
            "development_summary": development_summary,
            "test_summary": _test_summary(phases, reports["global_test_report"]),
            "qualification_summary": _qualification_summary(phases),
            "integrity_summary": _integrity_summary(reports),
            "health_status": health,
            "status": status,
            "critical_errors": critical,
            "warnings": warnings,
            "readiness_status": readiness,
            "release_blocking": release_blocking,
            "promotion_blocked": True,
        }
    )
    validate(artifact, "phase_health_panel.schema.yaml", "phase_health_panel")
    return result("P0.S6.M02", "phase_health_panel_builder", REQUIRED, {"phase_health_panel": artifact})


def _collected(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    if item.get("status") not in {"PASS", "WARN", "FAIL"} or not isinstance(item.get("phases"), list):
        raise ValueError("collected_phase_dashboard_payloads is invalid")
    return item


def _resolve_phase_health(phase: dict[str, Any], reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    item = dict(phase)
    if item["development_status"] == "NOT_STARTED":
        item["health_status"] = "UNKNOWN"
    elif item["health_status"] != "CRITICAL" and _phase_specific_failure(reports["global_test_report"], item["phase_id"]):
        item["health_status"] = "CRITICAL"
        item["test_status"] = "FAIL"
    item["readiness"], item["readiness_reasons"] = _readiness(item)
    item["release_blocking"] = item["readiness"] != "READY"
    item["status"] = "FAIL" if item["health_status"] == "CRITICAL" else "PASS"
    return item


def _phase_specific_failure(report: dict[str, Any], phase_id: str) -> bool:
    for field in ("phases", "phase_statuses"):
        values = report.get(field)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and item.get("phase_id") == phase_id and item.get("status") == "FAIL":
                return True
    return False


def _readiness(item: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if item["development_status"] != "IMPLEMENTED":
        reasons.append(item["development_status"])
    if item["test_status"] != "PASS":
        reasons.append(f"TEST_{item['test_status']}")
    if item["health_status"] in {"CRITICAL", "UNKNOWN"}:
        reasons.append(f"HEALTH_{item['health_status']}")
    if item["qualification_status"] != "QUALIFIED":
        reasons.append(f"QUALIFICATION_{item['qualification_status']}")
    return ("READY", []) if not reasons else ("NOT_READY", reasons)


def _critical_errors(phases: list[dict[str, Any]], reports: dict[str, dict[str, Any]]) -> list[str]:
    values = [f"{p['phase_id']}:CRITICAL" for p in phases if p["health_status"] == "CRITICAL"]
    for name, report in reports.items():
        if report["status"] == "FAIL":
            values.append(name)
    return sorted(set(values))


def _warnings(phases: list[dict[str, Any]], collected: dict[str, Any], reports: dict[str, dict[str, Any]]) -> list[str]:
    values = [f"{p['phase_id']}:NOT_READY" for p in phases if p["readiness"] != "READY" and p["health_status"] != "CRITICAL"]
    if collected.get("state_conflicts"):
        values.append("STATE_CONFLICT")
    if reports["code_quality_report"]["status"] == "FAIL":
        values.append("CODE_QUALITY")
    return sorted(set(values))


def _overall_health(phases: list[dict[str, Any]], critical: list[str], warnings: list[str]) -> str:
    if critical:
        return "CRITICAL"
    if warnings:
        return "WARNING"
    if phases and all(p["health_status"] == "HEALTHY" for p in phases):
        return "HEALTHY"
    return "UNKNOWN"


def _test_summary(phases: list[dict[str, Any]], global_report: dict[str, Any]) -> dict[str, Any]:
    counts = {name: 0 for name in ("NOT_RUN", "PARTIAL", "PASS", "FAIL")}
    for phase in phases:
        counts[phase["test_status"]] += 1
    return {"phase_counts": counts, "global_status": global_report["status"], "global_lineage_id": global_report["lineage_id"]}


def _qualification_summary(phases: list[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in ("NOT_ELIGIBLE", "ELIGIBLE", "RUNNING", "FAILED", "QUALIFIED")}
    for phase in phases:
        counts[phase["qualification_status"]] += 1
    return counts


def _integrity_summary(reports: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        "hash_status": reports["hash_integrity_report"]["status"],
        "code_quality_status": reports["code_quality_report"]["status"],
        "global_test_status": reports["global_test_report"]["status"],
    }
