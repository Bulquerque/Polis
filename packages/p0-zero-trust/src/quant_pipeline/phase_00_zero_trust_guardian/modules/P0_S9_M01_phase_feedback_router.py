from __future__ import annotations

from ._module_executor import PIPELINE_VERSION
from ._p0_s9_feedback import artifact, created_at, digest, envelope, lineage, require, validate_output
from ._p0_s9_models import merge_findings
from ._p0_s9_routing import collect_findings, expected_phase_ids, group_by_phase

INPUTS = ["release_gate_report", "phase_health_panel", "code_quality_report", "global_test_report"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require(inputs, config, INPUTS)
    sources = {name: artifact(inputs[name], name) for name in INPUTS}
    phase_ids = expected_phase_ids(sources)
    evidence = [_source_evidence(name, value) for name, value in sources.items()]
    findings, merged_count = merge_findings(collect_findings(sources, phase_ids))
    routed = group_by_phase(findings, phase_ids)
    phases = [_phase_feedback(phase_id, routed[phase_id]) for phase_id in phase_ids]
    panel = _build_panel(phases, findings, evidence, merged_count, config)
    validate_output(panel, "phase_zero_trust_feedback_panel.schema.yaml")
    return envelope("P0.S9.M01", "phase_feedback_router", INPUTS, {"phase_zero_trust_feedback_panel": panel})


def _source_evidence(name: str, value: dict) -> dict:
    return {
        "evidence_type": name,
        "artifact_id": value.get("artifact_id"),
        "lineage_id": lineage(value, name),
    }


def _phase_feedback(phase_id: str, findings: list[dict]) -> dict:
    blockers = [item for item in findings if item["readiness_blocking"] or item["release_blocking"]]
    advisories = [item for item in findings if item not in blockers]
    warnings = [item for item in advisories if item["severity"] == "WARNING"]
    notices = [item for item in findings if item["severity"] in {"NOTICE", "INFO"}]
    critical = [item for item in findings if item["severity"] == "CRITICAL"]
    status = "CRITICAL" if critical else "BLOCKED" if blockers else "WARNING" if warnings else "NOTICE" if notices else "PASS"
    return {
        "phase_id": phase_id,
        "status": status,
        "findings": findings,
        "blocking_errors": blockers,
        "advisories": advisories,
        "warnings": warnings,
        "notices": notices,
        "required_actions": [_action(item) for item in findings if item["action_required"]],
        "readiness_blocked": any(item["readiness_blocking"] for item in findings),
        "release_blocking": any(item["release_blocking"] for item in findings),
    }


def _action(item: dict) -> dict:
    return {
        "finding_id": item["finding_id"],
        "owner": item["owner_scope"],
        "action": item["suggested_action"],
    }


def _build_panel(phases: list[dict], findings: list[dict], evidence: list[dict], merged_count: int, config: dict) -> dict:
    blockers = [item for item in findings if item["readiness_blocking"] or item["release_blocking"]]
    advisories = [item for item in findings if item not in blockers]
    warnings = [item for item in advisories if item["severity"] == "WARNING"]
    notices = [item for item in findings if item["severity"] in {"NOTICE", "INFO"}]
    critical = [item for item in findings if item["severity"] == "CRITICAL"]
    actions = [_action(item) for item in findings if item["action_required"]]
    fingerprint = digest({"sources": evidence, "phases": phases})
    return {
        "artifact_id": f"phase-zero-trust-feedback-{fingerprint[:12]}",
        "phase_id": "P0-P9",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
        "source_evidence": evidence,
        "phase_count": len(phases),
        "phases": phases,
        "findings": findings,
        "blocking_errors": blockers,
        "advisories": advisories,
        "warnings": warnings,
        "notices": notices,
        "required_actions": actions,
        "blocking_count": len(blockers),
        "warning_count": len(warnings),
        "notice_count": len(notices),
        "finding_count": len(findings),
        "deduplicated_source_finding_count": merged_count,
        "critical_count": len(critical),
        "feedback_per_phase": True,
        "blocking_vs_warning_separated": True,
        "severity_impact_separated": True,
        "findings_deduplicated": True,
        "status": "CRITICAL" if critical else "BLOCKED" if blockers else "WARNING" if warnings else "NOTICE" if notices else "PASS",
        "readiness_blocking": any(item["readiness_blocking"] for item in findings),
        "release_blocking": any(item["release_blocking"] for item in findings),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
