"""Qualification and bundle consolidation for P3.S38."""
from __future__ import annotations

from collections.abc import Mapping

from .models import (
    CompanyOperationModeQualification, CompanyOperationReadinessPanel, CompanyToolBundle,
    ExtensionLineage, HandlerBundleManifest, HandlerQualificationRecord, QualificationStatus,
    ReadinessStatus, hashed_payload,
)


def combine_company_tool_bundle(*, bundles: tuple[HandlerBundleManifest, ...], lineage: ExtensionLineage):
    handlers = tuple(sorted((h for b in bundles for h in b.handlers), key=lambda h: h.operation_id))
    operations = [h.operation_id for h in handlers]
    if len(operations) != len(set(operations)):
        raise ValueError("company handler bundles contain duplicate operations")
    payload = {"bundle_version": "1.0.0", "handlers": handlers, "lineage": lineage}
    return CompanyToolBundle(**payload, bundle_hash=hashed_payload(payload))


def _report_passed(report: Mapping[str, object]) -> int:
    value = report.get("passed", 0)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def build_operation_mode_qualification(
    *, tool_bundle: CompanyToolBundle, readiness: CompanyOperationReadinessPanel,
    lineage: ExtensionLineage, contract_report: Mapping[str, object], leakage_report: Mapping[str, object],
):
    readiness_map = {(r.operation_id, r.mode_id): r for r in readiness.records}
    tests_pass = str(contract_report.get("status", "UNKNOWN")).upper() == "PASS"
    leakage_pass = str(leakage_report.get("status", "UNKNOWN")).upper() == "PASS"
    records = []
    for handler in tool_bundle.handlers:
        for mode in handler.supported_modes:
            ready = readiness_map.get((handler.operation_id, mode))
            if ready is None or ready.status is ReadinessStatus.BLOCKED_UPSTREAM:
                status, reasons = QualificationStatus.BLOCKED_UPSTREAM, ("P3RT-QUAL-COMPANY-BLOCKED-UPSTREAM",)
            elif not tests_pass or not leakage_pass:
                status, reasons = QualificationStatus.FAILED, ("P3RT-QUAL-COMPANY-TEST-FAILURE",)
            elif ready.status is ReadinessStatus.DEGRADED:
                status, reasons = QualificationStatus.DEGRADED, ready.reason_codes
            else:
                status, reasons = QualificationStatus.QUALIFIED_LOCAL, ()
            records.append(HandlerQualificationRecord(
                operation_id=handler.operation_id, mode_id=mode, status=status, handler_id=handler.handler_id,
                reason_codes=reasons, contract_tests_passed=_report_passed(contract_report),
                leakage_tests_passed=_report_passed(leakage_report),
            ))
    payload = {"records": tuple(records), "lineage": lineage}
    return CompanyOperationModeQualification(**payload, matrix_hash=hashed_payload(payload))
