"""Qualification assembly for P3.S39 operation and mode combinations."""
from __future__ import annotations

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .models import (
    ExtensionLineage,
    HandlerBundleManifest,
    HandlerQualificationRecord,
    QualificationStatus,
    QuantOperationModeQualification,
    QuantToolBundle,
    hashed_payload,
)


def _report_status(report: Mapping[str, object]) -> str:
    return str(report.get("status", "UNKNOWN")).upper()


def _passed(report: Mapping[str, object]) -> int:
    raw = report.get("passed", 0)
    return int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else 0


def _executed(report: Mapping[str, object]) -> int:
    raw = report.get("executed", 0)
    return int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else 0


def validate_qualification_report(report: Mapping[str, object], *, label: str) -> tuple[str, ...]:
    errors: list[str] = []
    if _report_status(report) != "PASS":
        errors.append(f"{label}:STATUS_NOT_PASS")
    executed = _executed(report)
    passed = _passed(report)
    if executed <= 0:
        errors.append(f"{label}:EXECUTED_EMPTY")
    if passed <= 0:
        errors.append(f"{label}:PASSED_EMPTY")
    if passed > executed > 0:
        errors.append(f"{label}:PASSED_EXCEEDS_EXECUTED")
    for field in ("evidence_id", "lineage_id"):
        if not str(report.get(field, "")).strip():
            errors.append(f"{label}:{field.upper()}_MISSING")
    evidence_payload = report.get("evidence_payload")
    evidence_hash = str(report.get("evidence_hash", ""))
    if evidence_payload is None:
        errors.append(f"{label}:EVIDENCE_PAYLOAD_MISSING")
    elif evidence_hash != content_hash(evidence_payload):
        errors.append(f"{label}:EVIDENCE_HASH_MISMATCH")
    report_hash = str(report.get("report_hash", ""))
    report_payload = dict(report)
    report_payload.pop("report_hash", None)
    if report_hash != content_hash(report_payload):
        errors.append(f"{label}:REPORT_HASH_MISMATCH")
    return tuple(errors)


def combine_quant_tool_bundle(
    *,
    bundles: tuple[HandlerBundleManifest, ...],
    lineage: ExtensionLineage,
) -> QuantToolBundle:
    handlers = tuple(
        sorted(
            (handler for bundle in bundles for handler in bundle.handlers),
            key=lambda handler: handler.operation_id,
        )
    )
    operations = [handler.operation_id for handler in handlers]
    if len(operations) != len(set(operations)):
        raise ValueError("quant handler bundles contain duplicate operations")
    payload = {
        "bundle_version": "1.0.0",
        "handlers": handlers,
        "lineage": lineage,
    }
    return QuantToolBundle(**payload, bundle_hash=hashed_payload(payload))


def build_operation_mode_qualification(
    *,
    tool_bundle: QuantToolBundle,
    lineage: ExtensionLineage,
    contract_report: Mapping[str, object],
    property_report: Mapping[str, object],
    leakage_report: Mapping[str, object],
) -> QuantOperationModeQualification:
    report_errors = (
        *validate_qualification_report(contract_report, label="CONTRACT"),
        *validate_qualification_report(property_report, label="PROPERTY"),
        *validate_qualification_report(leakage_report, label="LEAKAGE"),
    )
    statuses = {
        _report_status(contract_report),
        _report_status(property_report),
        _report_status(leakage_report),
    }
    if statuses == {"PASS"} and not report_errors:
        status = QualificationStatus.QUALIFIED_LOCAL
        reason_codes: tuple[str, ...] = ()
    elif "FAIL" in statuses:
        status = QualificationStatus.FAILED
        reason_codes = ("P3RT-QUAL-QUANT-TEST-FAILURE",)
    elif "BLOCKED_UPSTREAM" in statuses or report_errors:
        status = QualificationStatus.BLOCKED_UPSTREAM
        reason_codes = (
            "P3RT-QUAL-QUANT-BLOCKED-UPSTREAM",
            *report_errors,
        )
    else:
        status = QualificationStatus.DEGRADED
        reason_codes = ("P3RT-QUAL-QUANT-EVIDENCE-INCOMPLETE",)
    records = tuple(
        HandlerQualificationRecord(
            operation_id=handler.operation_id,
            mode_id=mode,
            status=status,
            handler_id=handler.handler_id,
            reason_codes=reason_codes,
            contract_tests_passed=_passed(contract_report),
            property_tests_passed=_passed(property_report),
            leakage_tests_passed=_passed(leakage_report),
        )
        for handler in tool_bundle.handlers
        for mode in handler.supported_modes
    )
    payload = {"records": records, "lineage": lineage}
    return QuantOperationModeQualification(
        records=records,
        lineage=lineage,
        matrix_hash=hashed_payload(payload),
    )
