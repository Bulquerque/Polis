from __future__ import annotations

from collections import Counter, defaultdict

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s9_feedback import artifact, created_at, digest, envelope, lineage, require, validate_output
from ._p0_s9_models import normalize_finding

INPUTS = ["phase_zero_trust_feedback_panel"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require(inputs, config, INPUTS)
    panel = artifact(inputs[INPUTS[0]], INPUTS[0])
    panel_lineage = lineage(panel, INPUTS[0])
    findings = panel.get("findings")
    if not isinstance(findings, list):
        legacy = panel.get("warnings", [])
        if not isinstance(legacy, list):
            raise ContractValidationError("feedback panel findings inventory is absent")
        if panel.get("warning_count") is not None and panel.get("warning_count") != len(legacy):
            raise ContractValidationError("feedback panel warning inventory is incomplete")
        findings = [_normalize_legacy(item) for item in legacy]
    advisories = [item for item in findings if not _blocks(item)]
    routed = [_route(item) for item in advisories]
    report = _build_report(routed, panel_lineage, config)
    validate_output(report, "nonblocking_warning_report.schema.yaml")
    return envelope("P0.S9.M03", "nonblocking_warning_dispatcher", INPUTS, {"nonblocking_warning_report": report})


def _normalize_legacy(item: dict) -> dict:
    phase_id = str(item.get("phase_id") or item.get("owner_phase") or "P0") if isinstance(item, dict) else "P0"
    return normalize_finding(item, phase_id, "phase_zero_trust_feedback_panel")


def _blocks(item: dict) -> bool:
    return item.get("readiness_blocking") is True or item.get("release_blocking") is True


def _route(item: dict) -> dict:
    if not isinstance(item, dict):
        raise ContractValidationError("advisory inventory contains malformed content")
    if item.get("severity") not in {"WARNING", "NOTICE", "INFO"}:
        raise ContractValidationError("nonblocking advisory has blocking/error severity")
    if not isinstance(item.get("owner_scope") or item.get("owner"), str):
        raise ContractValidationError("every advisory must have an owner")
    if item.get("action_required") is True and not item.get("suggested_action"):
        raise ContractValidationError("advisory requiring action must have suggested_action")
    return {
        **item,
        "routing_status": "ROUTED_TO_OWNER",
        "dispatch_status": "ROUTED",
        "external_dispatch_performed": False,
    }


def _build_report(advisories: list[dict], panel_lineage: str, config: dict) -> dict:
    warnings = [item for item in advisories if item["severity"] == "WARNING"]
    notices = [item for item in advisories if item["severity"] in {"NOTICE", "INFO"}]
    owners = defaultdict(list)
    for item in advisories:
        owners[item.get("owner_scope") or item.get("owner")].append(item["finding_id"])
    severities = Counter(item["severity"] for item in advisories)
    fingerprint = digest({"panel": panel_lineage, "advisories": advisories})
    owner_values = sorted(owners)
    return {
        "artifact_id": f"nonblocking-warning-report-{fingerprint[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
        "source_panel_lineage_id": panel_lineage,
        "owner": "multiple" if len(owner_values) > 1 else owner_values[0] if owner_values else "none",
        "action": "see advisories" if advisories else "none required",
        "advisory_count": len(advisories),
        "warning_count": len(warnings),
        "notice_count": len(notices),
        "advisories": advisories,
        "warnings": warnings,
        "notices": notices,
        "owner_groups": [{"owner_scope": owner, "finding_ids": sorted(ids), "advisory_count": len(ids)} for owner, ids in sorted(owners.items())],
        "severity_summary": dict(sorted(severities.items())),
        "warnings_have_owner": True,
        "warnings_have_action": all(not i.get("action_required") or i.get("suggested_action") for i in advisories),
        "warnings_not_release_blocking": True,
        "external_dispatch_performed": False,
        "status": "WARNING" if warnings else "NOTICE" if notices else "PASS",
        "release_blocking": False,
        "readiness_blocking": False,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
