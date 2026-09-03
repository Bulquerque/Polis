from __future__ import annotations

from typing import Any

from ._p0_s6_core import DEFAULT_PHASE_IDS, ContractValidationError, digest

DEVELOPMENT = {"NOT_STARTED", "IN_DEVELOPMENT", "IMPLEMENTED"}
TEST = {"NOT_RUN", "PARTIAL", "PASS", "FAIL"}
HEALTH = {"UNKNOWN", "HEALTHY", "WARNING", "CRITICAL"}
QUALIFICATION = {"NOT_ELIGIBLE", "ELIGIBLE", "RUNNING", "FAILED", "QUALIFIED"}
DOCUMENTATION = {"INCOMPLETE", "READY"}
READINESS = {"NOT_READY", "READY"}


def phase_ids(container: dict[str, Any]) -> list[str]:
    registry = container.get("registry_snapshot")
    if isinstance(registry, dict) and isinstance(registry.get("phases"), list):
        ids = [str(item.get("phase_id")) for item in registry["phases"] if isinstance(item, dict)]
        if ids and len(ids) == len(set(ids)):
            return sorted(ids, key=_phase_sort_key)
    return list(DEFAULT_PHASE_IDS)


def collect_phase_states(
    container: dict[str, Any],
    test_panel: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = phase_ids(container)
    runtime = _index_phase_records(container.get("phases"))
    development = _index_snapshot(container.get("development_state_snapshot"))
    qualification = _index_snapshot(container.get("qualification_state_snapshot"))
    tests = _index_phase_records(test_panel.get("phases"))
    return [
        _build_phase_state(pid, runtime.get(pid), development.get(pid), qualification.get(pid), tests.get(pid))
        for pid in expected
    ]


def _index_snapshot(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    phases = value.get("phases", value.get("phase_statuses", value))
    if isinstance(phases, dict):
        return {str(k): v for k, v in phases.items() if isinstance(v, dict)}
    return _index_phase_records(phases)


def _index_phase_records(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("phase_id"), str):
            continue
        pid = item["phase_id"]
        if pid in result:
            raise ContractValidationError(f"duplicate phase payload: {pid}")
        result[pid] = item
    return result


def _build_phase_state(
    phase_id: str,
    runtime: dict[str, Any] | None,
    development: dict[str, Any] | None,
    qualification: dict[str, Any] | None,
    tests: dict[str, Any] | None,
) -> dict[str, Any]:
    runtime = runtime or {}
    development = development or {}
    qualification = qualification or {}
    tests = tests or {}
    telemetry = "FULL" if runtime else "NONE"
    dev_status = _development_status(runtime, development)
    test_status = _test_status(runtime, tests, dev_status)
    health_status = _health_status(runtime, dev_status)
    qualification_status = _qualification_status(runtime, qualification, dev_status)
    documentation_status = _documentation_status(runtime, development)
    counts = _module_counts(runtime, development)
    readiness, reasons = _readiness(dev_status, test_status, health_status, qualification_status)
    source_lineage_ids = _lineages(runtime, development, qualification, tests)
    synthetic = not bool(runtime)
    control_status = "FAIL" if health_status == "CRITICAL" else "PASS"
    release_blocking = readiness != "READY"
    identity_payload = {"phase_id": phase_id, "development": dev_status, "qualification": qualification_status}
    identity_hash = digest(identity_payload)
    return {
        "phase_id": phase_id,
        "phase_name": _phase_name(phase_id, runtime, development),
        "artifact_id": runtime.get("artifact_id", f"dashboard-{phase_id.lower()}-{identity_hash[:12]}"),
        "lineage_id": runtime.get("lineage_id", f"sha256:{identity_hash}"),
        "status": control_status,
        "release_blocking": release_blocking,
        "planned": True,
        "telemetry_status": telemetry,
        "documentation_status": documentation_status,
        "development_status": dev_status,
        "test_status": test_status,
        "health_status": health_status,
        "qualification_status": qualification_status,
        "readiness": readiness,
        "module_counts": counts,
        "subphase_counts": _subphase_counts(runtime, development),
        "issue_counts": _issue_counts(runtime),
        "readiness_reasons": reasons,
        "source_lineage_ids": source_lineage_ids,
        "synthetic": synthetic,
    }


def _development_status(runtime: dict[str, Any], state: dict[str, Any]) -> str:
    for source in (state, runtime):
        explicit = source.get("development_status")
        if explicit in DEVELOPMENT:
            return explicit
        raw = str(source.get("implementation_status", source.get("operational_status", ""))).upper()
        if raw in {"IMPLEMENTED", "PHASE_QUALIFIED"}:
            return "IMPLEMENTED"
        if raw in {"IN_DEVELOPMENT", "IMPLEMENTING", "PARTIAL"}:
            return "IN_DEVELOPMENT"
    if runtime:
        return "IMPLEMENTED" if runtime.get("status") in {"PASS", "FAIL"} else "IN_DEVELOPMENT"
    return "NOT_STARTED"


def _test_status(runtime: dict[str, Any], tests: dict[str, Any], development: str) -> str:
    explicit = tests.get("test_status", runtime.get("test_status"))
    if explicit in TEST:
        return explicit
    failed = _int_value(tests.get("tests_failed", runtime.get("tests_failed")))
    passed = _int_value(tests.get("tests_passed", runtime.get("tests_passed")))
    status = tests.get("status")
    if failed > 0 or status == "FAIL":
        return "FAIL"
    if passed > 0 or status == "PASS":
        return "PASS"
    return "NOT_RUN" if development == "NOT_STARTED" else "PARTIAL"


def _health_status(runtime: dict[str, Any], development: str) -> str:
    explicit = runtime.get("health_status")
    if explicit in HEALTH:
        return explicit
    if runtime.get("status") == "FAIL":
        return "CRITICAL"
    if runtime.get("status") == "PASS":
        return "HEALTHY"
    return "UNKNOWN" if development == "NOT_STARTED" else "WARNING"


def _qualification_status(runtime: dict[str, Any], state: dict[str, Any], development: str) -> str:
    raw = str(state.get("qualification_status", runtime.get("qualification_status", ""))).upper()
    mapping = {
        "PHASE_QUALIFIED": "QUALIFIED",
        "QUALIFIED": "QUALIFIED",
        "IMPLEMENTED_NOT_QUALIFIED": "ELIGIBLE",
        "ELIGIBLE": "ELIGIBLE",
        "QUALIFICATION_RUNNING": "RUNNING",
        "RUNNING": "RUNNING",
        "QUALIFICATION_FAILED": "FAILED",
        "FAILED": "FAILED",
        "NOT_IMPLEMENTED": "NOT_ELIGIBLE",
        "NOT_ELIGIBLE": "NOT_ELIGIBLE",
    }
    if raw in mapping:
        return mapping[raw]
    return "ELIGIBLE" if development == "IMPLEMENTED" else "NOT_ELIGIBLE"


def _documentation_status(runtime: dict[str, Any], state: dict[str, Any]) -> str:
    for source in (state, runtime):
        explicit = source.get("documentation_status")
        if explicit in DOCUMENTATION:
            return explicit
        if source.get("requirement_status") == "PASS":
            return "READY"
    return "READY" if runtime else "INCOMPLETE"


def _module_counts(runtime: dict[str, Any], state: dict[str, Any]) -> dict[str, int]:
    source = state.get("module_counts") if isinstance(state.get("module_counts"), dict) else runtime.get("module_counts")
    source = source if isinstance(source, dict) else {}
    return {name: _int_value(source.get(name)) for name in ("planned", "implemented", "tested", "qualified")}


def _subphase_counts(runtime: dict[str, Any], state: dict[str, Any]) -> dict[str, int]:
    source = state.get("subphase_counts") if isinstance(state.get("subphase_counts"), dict) else runtime.get("subphase_counts")
    source = source if isinstance(source, dict) else {}
    return {name: _int_value(source.get(name)) for name in ("planned", "implemented", "tested", "qualified")}


def _issue_counts(runtime: dict[str, Any]) -> dict[str, int]:
    source = runtime.get("issue_counts") if isinstance(runtime.get("issue_counts"), dict) else {}
    return {name: _int_value(source.get(name)) for name in ("critical", "warning", "notice")}


def _readiness(development: str, tests: str, health: str, qualification: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if development != "IMPLEMENTED":
        reasons.append(development)
    if tests != "PASS":
        reasons.append(f"TEST_{tests}")
    if health in {"CRITICAL", "UNKNOWN"}:
        reasons.append(f"HEALTH_{health}")
    if qualification != "QUALIFIED":
        reasons.append(f"QUALIFICATION_{qualification}")
    return ("READY", []) if not reasons else ("NOT_READY", reasons)


def _lineages(*sources: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in sources:
        lineage = source.get("lineage_id")
        if isinstance(lineage, str) and lineage.startswith("sha256:") and lineage not in values:
            values.append(lineage)
    return values


def _phase_name(phase_id: str, runtime: dict[str, Any], state: dict[str, Any]) -> str:
    value = runtime.get("phase_name", state.get("phase_name"))
    return str(value) if value else phase_id


def _int_value(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _phase_sort_key(value: str) -> tuple[int, str]:
    if value.startswith("P") and value[1:].isdigit():
        return int(value[1:]), value
    return 10_000, value


def aggregate_counts(phases: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "phases_total": len(phases),
        "phases_not_started": 0,
        "phases_in_development": 0,
        "phases_implemented": 0,
        "phases_qualified": 0,
        "modules": {"planned": 0, "implemented": 0, "tested": 0, "qualified": 0},
    }
    for phase in phases:
        dev = phase["development_status"]
        if dev == "NOT_STARTED":
            summary["phases_not_started"] += 1
        elif dev == "IN_DEVELOPMENT":
            summary["phases_in_development"] += 1
        elif dev == "IMPLEMENTED":
            summary["phases_implemented"] += 1
        if phase["qualification_status"] == "QUALIFIED":
            summary["phases_qualified"] += 1
        for key in summary["modules"]:
            summary["modules"][key] += phase["module_counts"][key]
    return summary
