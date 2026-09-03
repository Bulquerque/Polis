"""P9.S4.M08 — metric reconciliation, registry, and publication quality gate."""

from __future__ import annotations

from .bundle_models import (
    InstitutionalMetricPanel,
    MetricLimitation,
    MetricQualityRequest,
    MetricQualityResult,
    MetricQualityReceipt,
    QualityState,
)
from .common import MetricStatus, content_sha256
from .reason_codes import ReasonCode


def _all_panels(request: MetricQualityRequest):
    panels = [
        request.returns.return_metrics,
        request.distribution.volatility,
        request.tails.metrics,
        request.drawdowns.metrics,
        request.risk_adjusted.metrics,
        request.execution.execution,
    ]
    if request.factors is not None:
        panels.append(request.factors.exposures)
    return panels


def reconcile_metrics(request: MetricQualityRequest) -> MetricQualityResult:
    """Reject registry drift, identity conflicts, and incomplete metric provenance."""

    panels = _all_panels(request)
    identity = request.returns.return_metrics.identity
    reason_codes: set[str] = set()
    check_ids: list[str] = []
    limitations: list[MetricLimitation] = []
    metrics = []

    identities_match = all(panel.identity == identity for panel in panels)
    check_ids.append("identity_consistency")
    if not identities_match:
        reason_codes.add(ReasonCode.METRIC_RECONCILIATION_FAILED.value)

    if request.policy.require_factor_panel and request.factors is None:
        reason_codes.add(ReasonCode.FACTOR_DATA_UNAVAILABLE.value)
    check_ids.append("factor_requirement")

    registry_valid = True
    seen = set()
    for panel in panels:
        for metric in panel.metrics:
            key = (metric.metric_id, metric.metric_version, metric.gross_net.value)
            if key in seen:
                registry_valid = False
                reason_codes.add(ReasonCode.METRIC_RECONCILIATION_FAILED.value)
                continue
            seen.add(key)
            try:
                entry = request.registry.get(metric.metric_id, metric.metric_version)
            except KeyError:
                registry_valid = False
                reason_codes.add(ReasonCode.METRIC_REGISTRY_DRIFT.value)
                continue
            if entry.unit != metric.unit.value or metric.gross_net.value not in entry.allowed_gross_net:
                registry_valid = False
                reason_codes.add(ReasonCode.UNIT_CONFLICT.value)
            metrics.append(metric)
            for limitation in metric.limitations:
                limitations.append(
                    MetricLimitation(
                        metric_id=metric.metric_id,
                        limitation=limitation,
                        severity="WARNING" if metric.status is not MetricStatus.INVALID else "BLOCKER",
                    )
                )
            if metric.status in {
                MetricStatus.LIMITED,
                MetricStatus.UNAVAILABLE,
                MetricStatus.INSUFFICIENT_SAMPLE,
                MetricStatus.UNDEFINED,
            }:
                limitations.append(
                    MetricLimitation(
                        metric_id=metric.metric_id,
                        limitation=f"metric status is {metric.status.value}",
                        severity="WARNING",
                    )
                )
            if metric.status is MetricStatus.INVALID:
                reason_codes.add(ReasonCode.METRIC_RECONCILIATION_FAILED.value)
    check_ids.append("registry_and_units")

    expected_return_hash = content_sha256(
        {
            "wealth": request.returns.wealth_path.content_sha256,
            "series": request.returns.return_series.content_sha256,
            "metrics": request.returns.return_metrics.content_sha256,
        }
    )
    check_ids.append("return_reconciliation_hash")
    if expected_return_hash != request.returns.reconciliation_sha256:
        reason_codes.add(ReasonCode.METRIC_RECONCILIATION_FAILED.value)

    if request.s4_module_receipts:
        module_ids = [receipt.module_id for receipt in request.s4_module_receipts]
        expected = {f"P9.S4.M{index:02d}" for index in range(1, 8)}
        if set(module_ids) != expected or len(module_ids) != 7:
            reason_codes.add(ReasonCode.SUBPHASE_INCOMPLETE.value)
    check_ids.append("module_receipt_conservation")

    if request.policy.require_all_core_metrics_qualified:
        if any(metric.status is not MetricStatus.QUALIFIED for metric in metrics):
            reason_codes.add(ReasonCode.METRIC_RECONCILIATION_FAILED.value)
    check_ids.append("core_metric_qualification")

    if reason_codes:
        state = QualityState.INVALID
    elif limitations or not registry_valid:
        state = QualityState.QUALIFIED_WITH_LIMITATIONS
    else:
        state = QualityState.QUALIFIED

    ordered_metrics = tuple(
        sorted(
            metrics,
            key=lambda metric: (
                metric.metric_id,
                metric.metric_version,
                metric.gross_net.value,
            ),
        )
    )
    panel_body = {
        "panel_id": f"institutional-metrics-{identity.handoff_id}",
        "panel_version": "1.0.0",
        "identity": identity,
        "metrics": ordered_metrics,
        "diagnostics": (),
        "limitations": tuple(sorted({item.limitation for item in limitations})),
        "metric_count": len(ordered_metrics),
    }
    panel = InstitutionalMetricPanel(**panel_body, content_sha256=content_sha256(panel_body))
    receipt_body = {
        "identity": identity,
        "state": state,
        "check_ids": tuple(check_ids),
        "reason_codes": tuple(sorted(reason_codes)),
        "limitations": tuple(limitations),
    }
    receipt = MetricQualityReceipt(**receipt_body, content_sha256=content_sha256(receipt_body))
    return MetricQualityResult(panel=panel, receipt=receipt)
