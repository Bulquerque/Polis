from __future__ import annotations

from collections import Counter, defaultdict

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s9_feedback import artifact, created_at, digest, envelope, lineage, require, validate_output
from ._p0_s9_models import normalize_finding, priority

INPUTS = ["phase_zero_trust_feedback_panel"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require(inputs, config, INPUTS)
    panel = artifact(inputs[INPUTS[0]], INPUTS[0])
    panel_lineage = lineage(panel, INPUTS[0])
    findings = panel.get("findings")
    if not isinstance(findings, list):
        legacy = panel.get("blocking_errors", [])
        if not isinstance(legacy, list):
            raise ContractValidationError("feedback panel findings inventory is absent")
        findings = [_normalize_legacy(item) for item in legacy]
    blockers = [item for item in findings if _blocks(item)]
    if panel.get("blocking_count") is not None and panel.get("blocking_count") != len(blockers):
        raise ContractValidationError("feedback panel blocking inventory is incomplete")
    routed = [_route(item) for item in blockers]
    report = _build_report(routed, panel_lineage, config)
    validate_output(report, "blocking_issue_report.schema.yaml")
    return envelope("P0.S9.M02", "blocking_issue_dispatcher", INPUTS, {"blocking_issue_report": report})


def _normalize_legacy(item: dict) -> dict:
    phase_id = str(item.get("phase_id") or item.get("owner_phase") or "P0") if isinstance(item, dict) else "P0"
    return normalize_finding(item, phase_id, "phase_zero_trust_feedback_panel")


def _blocks(item: dict) -> bool:
    return item.get("readiness_blocking") is True or item.get("release_blocking") is True


def _route(issue: dict) -> dict:
    if not isinstance(issue, dict) or not isinstance(issue.get("owner_scope") or issue.get("owner"), str):
        raise ContractValidationError("every blocking issue must have an owner")
    if issue.get("action_required") is True and not issue.get("suggested_action"):
        raise ContractValidationError("blocking issue requiring action must have suggested_action")
    return {
        **issue,
        "priority": priority(issue),
        "routing_status": "ROUTED_TO_OWNER",
        "dispatch_status": "ROUTED",
        "external_dispatch_performed": False,
    }


def _build_report(issues: list[dict], panel_lineage: str, config: dict) -> dict:
    owners = defaultdict(list)
    for item in issues:
        owners[item.get("owner_scope") or item.get("owner")].append(item["finding_id"])
    conditions = Counter(item.get("condition_type", "UNKNOWN") for item in issues)
    priorities = Counter(item["priority"] for item in issues)
    fingerprint = digest({"panel": panel_lineage, "issues": issues})
    owner_values = sorted(owners)
    return {
        "artifact_id": f"blocking-issue-report-{fingerprint[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
        "source_panel_lineage_id": panel_lineage,
        "owner": "multiple" if len(owner_values) > 1 else owner_values[0] if owner_values else "none",
        "action": "see routed issues" if issues else "none required",
        "issue_count": len(issues),
        "issues": issues,
        "owner_groups": [{"owner_scope": owner, "finding_ids": sorted(ids), "issue_count": len(ids)} for owner, ids in sorted(owners.items())],
        "condition_summary": dict(sorted(conditions.items())),
        "priority_summary": dict(sorted(priorities.items())),
        "blocking_errors_have_owner": True,
        "blocking_errors_have_action": all(not i.get("action_required") or i.get("suggested_action") for i in issues),
        "impact_based_blocking": True,
        "external_dispatch_performed": False,
        "status": "BLOCKED" if issues else "PASS",
        "readiness_blocking": any(i.get("readiness_blocking") for i in issues),
        "release_blocking": any(i.get("release_blocking") for i in issues),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
