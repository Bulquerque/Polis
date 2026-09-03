from __future__ import annotations

import re

from ._s5_ast_metrics import infer_phase_from_path
from ._s5_core import envelope, module_result, require_config, require_inputs
from ._s5_schema import validate_artifact

_SOURCES = (
    ("duplicate_file_report", "P0.S5.M01"),
    ("monolith_report", "P0.S5.M02"),
    ("forbidden_import_report", "P0.S5.M03"),
    ("hidden_global_state_report", "P0.S5.M04"),
    ("module_contract_coverage_report", "P0.S5.M05"),
)

_PHASE_ID = re.compile(r"^(P\d+)\.S\d+\.M\d+$")


def _summary(name: str, producer: str, report: dict) -> dict:
    if not isinstance(report, dict) or set(report) == {"source"}:
        raise ValueError(f"{name} must be a materialized report")
    required = {"artifact_id", "lineage_id", "status", "release_blocking", "promotion_blocked"}
    if required - set(report):
        raise ValueError(f"{name} is missing report control fields")
    if report["status"] not in {"PASS", "FAIL"} or not isinstance(report["release_blocking"], bool):
        raise ValueError(f"{name} has invalid status controls")
    if (report["status"] == "PASS") == report["release_blocking"]:
        raise ValueError(f"{name} has inconsistent status/release_blocking state")
    return {
        "report_name": name, "producer_module_id": producer,
        "artifact_id": report["artifact_id"], "lineage_id": report["lineage_id"],
        "status": report["status"], "release_blocking": report["release_blocking"],
    }


def _phase_from_module(module_id: str | None) -> str | None:
    match = _PHASE_ID.match(module_id or "")
    return match.group(1) if match else None


def _raw_findings(report_name: str, report: dict) -> list[dict]:
    for key in ("findings", "violations", "duplicate_groups"):
        value = report.get(key)
        if isinstance(value, list) and value:
            return value
    if report.get("release_blocking"):
        return [{"message": f"{report_name} is blocking without itemized findings"}]
    return []


def _finding_phases(item: dict) -> set[str]:
    phases: set[str] = set()
    module_id = item.get("module_id")
    phase = _phase_from_module(module_id if isinstance(module_id, str) else None)
    if phase:
        phases.add(phase)
    path = item.get("path")
    if isinstance(path, str):
        inferred = infer_phase_from_path(path)
        if inferred:
            phases.add(inferred)
    paths = item.get("paths")
    if isinstance(paths, list):
        for candidate in paths:
            if isinstance(candidate, str):
                inferred = infer_phase_from_path(candidate)
                if inferred:
                    phases.add(inferred)
    return phases or {"P0"}


def _append_phase_finding(findings_by_phase, report_name, index, item):
    phases = _finding_phases(item) if isinstance(item, dict) else {"P0"}
    message = report_name
    if isinstance(item, dict):
        message = str(item.get("kind") or item.get("classification") or item.get("message") or report_name)
    for phase in phases:
        findings_by_phase[phase].append({
            "finding_id": f"CQ-{report_name}-{index}-{phase}",
            "severity": "BLOCKING",
            "message": message,
            "owner": phase,
            "action": "Resolve the referenced code-quality finding",
        })


def _phase_panels(inputs: dict, blocking_reports: list[str]) -> list[dict]:
    findings_by_phase = {f"P{i}": [] for i in range(10)}
    for report_name in blocking_reports:
        for index, item in enumerate(_raw_findings(report_name, inputs[report_name])):
            _append_phase_finding(findings_by_phase, report_name, index, item)
    return [
        {"phase_id": phase, "status": "FAIL" if findings_by_phase[phase] else "PASS", "findings": findings_by_phase[phase]}
        for phase in (f"P{i}" for i in range(10))
    ]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, {name for name, _ in _SOURCES})
    config = require_config(config)
    summaries = [_summary(name, producer, inputs[name]) for name, producer in _SOURCES]
    blocking = [item["report_name"] for item in summaries if item["release_blocking"]]
    artifact = envelope("code_quality_report", {"summaries": summaries, "blocking": blocking}, config)
    artifact.update({
        "source_report_count": len(summaries),
        "source_reports": summaries,
        "blocking_report_count": len(blocking),
        "blocking_reports": blocking,
        "quality_status": "FAIL" if blocking else "PASS",
        "status": "FAIL" if blocking else "PASS",
        "phases": _phase_panels(inputs, blocking),
        "blocking_quality_issue": bool(blocking),
        "release_blocking": bool(blocking),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    })
    validate_artifact(artifact, "code_quality_report.schema.yaml", "code_quality_report")
    return module_result(
        "P0.S5.M06", "code_style_quality_reporter", [name for name, _ in _SOURCES], "code_quality_report", artifact,
    )
