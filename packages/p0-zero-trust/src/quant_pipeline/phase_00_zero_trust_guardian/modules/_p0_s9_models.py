from __future__ import annotations

from typing import Any
import re

from ._module_executor import ContractValidationError
from ._p0_s9_feedback import (
    BLOCK,
    CONDITIONS,
    NO_BLOCK,
    NO_RELEASE_BLOCK,
    RELEASE_BLOCK,
    SEVERITIES,
    digest,
)

OWNER_RE = re.compile(r"^(P\d+)(?:\.(S\d+))?(?:\.(M\d+))?$")


def normalize_finding(raw: dict[str, Any], phase_id: str, source: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractValidationError(f"{source}.{phase_id} has malformed finding")
    finding_id = _required_text(raw.get("finding_id"), "finding_id")
    message = _required_text(raw.get("message"), "message")
    if "owner" in raw:
        owner = _required_text(raw.get("owner"), "owner")
    else:
        owner = _required_text(raw.get("owner_module") or raw.get("owner_phase") or phase_id, "owner")
    severity, legacy = _severity(raw)
    readiness, release = _impacts(raw, legacy)
    _validate_impact_severity(severity, readiness, release)
    condition = _condition(raw, severity, readiness)
    reason_code = str(raw.get("reason_code") or _reason_from_id(finding_id)).upper()
    action = str(raw.get("suggested_action") or raw.get("action") or "").strip()
    default_action_required = legacy == "BLOCKING" or (bool(action) and severity not in {"NOTICE", "INFO"})
    action_required = bool(raw.get("action_required", default_action_required))
    if action_required and not action:
        raise ContractValidationError("action_required finding must have suggested_action/action")
    owner_fields = _owner_fields(owner, phase_id, raw)
    subject = str(raw.get("affected_artifact") or raw.get("subject") or message).strip()
    semantic = {
        "reason_code": reason_code,
        "owner": owner_fields["owner_scope"],
        "subject": subject,
        "condition_type": condition,
        "readiness_impact": readiness,
        "release_impact": release,
    }
    fingerprint = digest(semantic)
    return {
        "finding_id": finding_id,
        "finding_fingerprint": f"sha256:{fingerprint}",
        "reason_code": reason_code,
        "severity": severity,
        "legacy_severity": legacy,
        "condition_type": condition,
        "readiness_impact": readiness,
        "release_impact": release,
        **owner_fields,
        "message": message,
        "action_required": action_required,
        "suggested_action": action or None,
        "affected_artifact": raw.get("affected_artifact"),
        "source_evidence": [{"source": source, "source_finding_id": finding_id}],
        "release_blocking": release == RELEASE_BLOCK,
        "readiness_blocking": readiness == BLOCK,
    }


def merge_findings(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_fingerprint: dict[str, dict[str, Any]] = {}
    by_id: dict[str, str] = {}
    merged = 0
    for item in findings:
        fingerprint = item["finding_fingerprint"]
        finding_id = item["finding_id"]
        if finding_id in by_id and by_id[finding_id] != fingerprint:
            raise ContractValidationError(f"conflicting finding_id: {finding_id}")
        by_id[finding_id] = fingerprint
        if fingerprint not in by_fingerprint:
            by_fingerprint[fingerprint] = dict(item)
            continue
        current = by_fingerprint[fingerprint]
        current["source_evidence"] = _merge_sources(current["source_evidence"], item["source_evidence"])
        current["finding_id"] = min(current["finding_id"], item["finding_id"])
        current["severity"] = _max_severity(current["severity"], item["severity"])
        merged += 1
    return sorted(by_fingerprint.values(), key=_finding_sort_key), merged


def priority(item: dict[str, Any]) -> str:
    if item["severity"] == "CRITICAL":
        return "P0"
    if item["severity"] == "ERROR" and item["release_blocking"]:
        return "P1"
    if item["release_blocking"] or item["readiness_blocking"]:
        return "P2"
    return "P3"


def _severity(raw: dict[str, Any]) -> tuple[str, str | None]:
    value = str(raw.get("severity") or "").upper()
    if value == "BLOCKING":
        return "ERROR", "BLOCKING"
    if value in SEVERITIES:
        return value, value if value == "WARNING" else None
    raise ContractValidationError(f"unsupported finding severity: {value or '<empty>'}")


def _impacts(raw: dict[str, Any], legacy: str | None) -> tuple[str, str]:
    readiness = str(raw.get("readiness_impact") or "")
    release = str(raw.get("release_impact") or "")
    if readiness not in {BLOCK, NO_BLOCK}:
        readiness = BLOCK if legacy == "BLOCKING" or raw.get("readiness_blocking") is True else NO_BLOCK
    if release not in {RELEASE_BLOCK, NO_RELEASE_BLOCK}:
        release = RELEASE_BLOCK if legacy == "BLOCKING" or raw.get("release_blocking") is True else NO_RELEASE_BLOCK
    return readiness, release



def _validate_impact_severity(severity: str, readiness: str, release: str) -> None:
    if severity in {"WARNING", "INFO"} and (readiness == BLOCK or release == RELEASE_BLOCK):
        raise ContractValidationError(f"{severity} finding cannot block readiness or release")


def _condition(raw: dict[str, Any], severity: str, readiness: str) -> str:
    value = str(raw.get("condition_type") or "").upper()
    if value in CONDITIONS:
        return value
    if severity == "CRITICAL":
        return "FAILURE"
    if readiness == BLOCK:
        return "INCOMPLETE" if severity in {"NOTICE", "INFO"} else "FAILURE"
    return "FAILURE" if severity == "ERROR" else "INCOMPLETE"


def _owner_fields(owner: str, phase_id: str, raw: dict[str, Any]) -> dict[str, str | None]:
    owner_phase = str(raw.get("owner_phase") or "").strip() or None
    owner_subphase = str(raw.get("owner_subphase") or "").strip() or None
    owner_module = str(raw.get("owner_module") or "").strip() or None
    match = OWNER_RE.fullmatch(owner)
    if match:
        owner_phase = owner_phase or match.group(1)
        if match.group(2):
            owner_subphase = owner_subphase or f"{match.group(1)}.{match.group(2)}"
        if match.group(3):
            owner_module = owner_module or owner
    owner_phase = owner_phase or phase_id
    owner_scope = owner_module or owner_subphase or owner_phase or owner
    return {
        "owner": owner,
        "owner_phase": owner_phase,
        "owner_subphase": owner_subphase,
        "owner_module": owner_module,
        "owner_scope": owner_scope,
    }


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"finding {field} must be non-empty")
    return value.strip()


def _reason_from_id(finding_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", finding_id).strip("_")
    return value or "UNSPECIFIED_FINDING"


def _merge_sources(left: list[dict], right: list[dict]) -> list[dict]:
    items = left + right
    keyed = {(item.get("source"), item.get("source_finding_id")): item for item in items}
    return [keyed[key] for key in sorted(keyed)]


def _max_severity(left: str, right: str) -> str:
    rank = {"INFO": 0, "NOTICE": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    return left if rank[left] >= rank[right] else right


def _finding_sort_key(item: dict[str, Any]) -> tuple:
    rank = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "NOTICE": 3, "INFO": 4}
    return (rank[item["severity"]], item["owner_scope"], item["reason_code"], item["finding_id"])
