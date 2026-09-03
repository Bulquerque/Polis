"""Readiness resolution by operation and research mode."""
from __future__ import annotations

from collections.abc import Mapping

from .models import (
    CompanyMode, CompanyOperationReadinessPanel, ExtensionLineage, ReadinessRecord, ReadinessStatus, hashed_payload,
)

_OPERATION_VIEWS = {
    "get_profile": ("company_profile",),
    "get_financial_statements": ("financial_statements",),
    "get_fundamental_snapshot": ("financial_statements",),
    "get_guidance": ("company_guidance",),
    "get_capital_allocation": ("financial_statements", "corporate_actions"),
    "get_peers": ("company_peers",),
    "calculate_valuation": (),
}


def available_views(manifest: object) -> set[str]:
    if not isinstance(manifest, Mapping):
        return set()
    raw = manifest.get("views", manifest.get("records", ()))
    if isinstance(raw, Mapping):
        return {str(k) for k, v in raw.items() if not isinstance(v, Mapping) or str(v.get("status", "READY")) != "BLOCKED"}
    result = set()
    for item in raw if isinstance(raw, (tuple, list)) else ():
        if isinstance(item, Mapping):
            view_id = item.get("view_id") or item.get("artifact_name")
            if view_id and str(item.get("status", "READY")) not in {"BLOCKED", "FAILED"}:
                result.add(str(view_id))
    return result


def build_readiness_panel(*, view_manifest: object, lineage: ExtensionLineage) -> CompanyOperationReadinessPanel:
    available = available_views(view_manifest)
    records = []
    for operation_id, required in _OPERATION_VIEWS.items():
        for mode in CompanyMode:
            required_mode = required
            version_required = mode is CompanyMode.FORENSIC
            missing = tuple(sorted(set(required_mode) - available))
            if operation_id == "calculate_valuation" and mode in {CompanyMode.QUICK_CHECK, CompanyMode.STANDARD_REVIEW}:
                status, reasons = ReadinessStatus.AVAILABLE, ()
            elif missing:
                status, reasons = ReadinessStatus.BLOCKED_UPSTREAM, ("P3RT-UPSTREAM-COMPANY-VIEW-MISSING",)
            elif version_required and "company_restatement_history" not in available:
                status, reasons = ReadinessStatus.BLOCKED_UPSTREAM, ("P3RT-UPSTREAM-COMPANY-VERSION-HISTORY-MISSING",)
            else:
                status, reasons = ReadinessStatus.AVAILABLE, ()
            records.append(ReadinessRecord(
                operation_id=operation_id, mode_id=mode, status=status, required_view_ids=required_mode,
                available_view_ids=tuple(sorted(set(required_mode) & available)), missing_view_ids=missing,
                version_history_required=version_required, reason_codes=reasons,
            ))
    payload = {"records": tuple(records), "lineage": lineage}
    return CompanyOperationReadinessPanel(**payload, panel_hash=hashed_payload(payload))
