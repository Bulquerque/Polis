from __future__ import annotations

from ._p0_s6_core import envelope, require_config, require_inputs, result, s6_control, source_control, source_summary, validate

REQUIRED = [
    "phase_health_panel",
    "forbidden_connection_report",
    "io_compatibility_report",
    "zero_trust_evidence_package",
]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, set(REQUIRED))
    config = require_config(config)
    panel = s6_control(inputs[REQUIRED[0]], REQUIRED[0])
    reports = {name: source_control(inputs[name], name) for name in REQUIRED[1:]}
    _validate_panel(panel)
    sources = [source_summary(panel, REQUIRED[0])] + [source_summary(reports[name], name) for name in REQUIRED[1:]]
    zero_trust = _zero_trust_summary(panel, reports)
    alerts = _alert_summary(panel, reports)
    readiness = _readiness_summary(panel)
    blocking = _blocking_sources(panel, reports)
    status = _global_status(panel, reports)
    tower = _tower(panel, zero_trust, alerts, readiness, blocking, status, config)
    pipeline = _pipeline_report(panel, sources, readiness, blocking, status, config)
    zero = _zero_trust_report(zero_trust, sources, blocking, status, config)
    outputs = {
        "global_control_tower_payload": tower,
        "pipeline_health_report": pipeline,
        "zero_trust_health_report": zero,
    }
    for name, artifact in outputs.items():
        validate(artifact, f"{name}.schema.yaml", name)
    return result("P0.S6.M03", "global_control_tower_builder", REQUIRED, outputs)


def _validate_panel(panel: dict) -> None:
    if not isinstance(panel.get("phase_statuses"), list) or panel.get("phase_count") != len(panel["phase_statuses"]):
        raise ValueError("phase_health_panel is partial or inconsistent")


def _zero_trust_summary(panel: dict, reports: dict[str, dict]) -> dict[str, str]:
    integrity = panel.get("integrity_summary", {})
    evidence = reports["zero_trust_evidence_package"]
    return {
        "forbidden_connections": reports["forbidden_connection_report"]["status"],
        "io_compatibility": reports["io_compatibility_report"]["status"],
        "schema_status": str(evidence.get("schema_status", reports["io_compatibility_report"].get("schema_status", "UNKNOWN"))),
        "hash_status": str(integrity.get("hash_status", "UNKNOWN")),
        "code_quality_status": str(integrity.get("code_quality_status", "UNKNOWN")),
        "evidence_status": evidence["status"],
    }


def _alert_summary(panel: dict, reports: dict[str, dict]) -> dict[str, int]:
    critical = len(panel.get("critical_errors", [])) + sum(1 for report in reports.values() if report["status"] == "FAIL")
    warning = len(panel.get("warnings", []))
    notice = sum(1 for phase in panel["phase_statuses"] if phase["development_status"] == "NOT_STARTED")
    return {"critical": critical, "warning": warning, "notice": notice}


def _readiness_summary(panel: dict) -> dict[str, object]:
    ready = [p["phase_id"] for p in panel["phase_statuses"] if p["readiness"] == "READY"]
    not_ready = [p["phase_id"] for p in panel["phase_statuses"] if p["readiness"] != "READY"]
    return {"ready_phase_count": len(ready), "not_ready_phase_count": len(not_ready), "ready_phases": ready, "not_ready_phases": not_ready}


def _blocking_sources(panel: dict, reports: dict[str, dict]) -> list[str]:
    values = []
    if panel.get("release_blocking") is True:
        values.append("phase_health_panel")
    values.extend(name for name, report in reports.items() if report["release_blocking"])
    return sorted(set(values))


def _global_status(panel: dict, reports: dict[str, dict]) -> str:
    if panel["release_blocking"] or any(report["release_blocking"] for report in reports.values()):
        return "FAIL"
    return "PASS"


def _tower(panel: dict, zero_trust: dict, alerts: dict, readiness: dict, blocking: list[str], status: str, config: dict) -> dict:
    payload = {"panel": panel["lineage_id"], "zero_trust": zero_trust, "readiness": readiness}
    artifact = envelope("global_control_tower_payload", payload, config)
    artifact.update(
        {
            "phase_count": panel["phase_count"],
            "phase_statuses": panel["phase_statuses"],
            "development_summary": panel["development_summary"],
            "test_summary": panel["test_summary"],
            "qualification_summary": panel["qualification_summary"],
            "integrity_summary": panel["integrity_summary"],
            "alert_summary": alerts,
            "readiness_summary": readiness,
            "zero_trust_summary": zero_trust,
            "schema_status": zero_trust["schema_status"],
            "hash_status": zero_trust["hash_status"],
            "release_readiness": "READY" if not readiness["not_ready_phases"] and not blocking else "BLOCKED",
            "blocking_sources": blocking,
            "status": status,
            "release_blocking": bool(blocking),
            "promotion_blocked": True,
        }
    )
    return artifact


def _pipeline_report(panel: dict, sources: list[dict], readiness: dict, blocking: list[str], status: str, config: dict) -> dict:
    artifact = envelope("pipeline_health_report", {"panel": panel["lineage_id"], "readiness": readiness}, config)
    artifact.update(
        {
            "phase_count": panel["phase_count"],
            "phase_statuses": panel["phase_statuses"],
            "development_summary": panel["development_summary"],
            "test_summary": panel["test_summary"],
            "qualification_summary": panel["qualification_summary"],
            "readiness_summary": readiness,
            "status": status,
            "source_reports": sources,
            "blocking_sources": blocking,
            "release_blocking": bool(blocking),
            "promotion_blocked": True,
        }
    )
    return artifact


def _zero_trust_report(zero_trust: dict, sources: list[dict], blocking: list[str], status: str, config: dict) -> dict:
    artifact = envelope("zero_trust_health_report", zero_trust, config)
    artifact.update(
        {
            "zero_trust_summary": zero_trust,
            "status": status,
            "source_reports": sources,
            "blocking_sources": [x for x in blocking if not x.startswith("P")],
            "release_blocking": any(not x.startswith("P") for x in blocking),
            "promotion_blocked": True,
        }
    )
    return artifact
