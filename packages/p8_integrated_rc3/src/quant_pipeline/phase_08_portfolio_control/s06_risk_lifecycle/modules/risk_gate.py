from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import (
    canonical_sha256,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import DecisionReadyRiskBundle

from ..domain.risk_evaluation import evaluate_target
from ..domain.target import is_no_action, target_paths
from ..models.artifacts import IndependentRiskGateReport
from ..models.enums import RiskGateStatus
from ..models.policies import RiskGatePolicy


def _hash_report(report: IndependentRiskGateReport) -> IndependentRiskGateReport:
    unsigned = report.model_copy(update={"report_hash": "0" * 64})
    return report.model_copy(update={"report_hash": canonical_sha256(unsigned)})


def _no_action_report(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
) -> IndependentRiskGateReport:
    return _hash_report(
        IndependentRiskGateReport(
            status=RiskGateStatus.NO_ACTION_VALID,
            horizon_metrics=(),
            exposure_limits=(),
            optimizer_claimed_feasible=True,
            independently_feasible=True,
            maximum_optimizer_risk_discrepancy=0,
            decision_snapshot_hash=risk_bundle.payload.decision_snapshot_hash,
            target_hash=s5_bundle.payload.discrete_target.discrete_hash,
            report_hash="0" * 64,
            reason_codes=("NO_ACTION_VALID",),
        )
    )


def _block_on_discrepancy(
    report: IndependentRiskGateReport,
) -> IndependentRiskGateReport:
    reasons = tuple(sorted(set(report.reason_codes) | {"OPTIMIZER_RISK_DISCREPANCY"}))
    blocked = report.model_copy(
        update={
            "status": RiskGateStatus.RISK_BLOCKED,
            "independently_feasible": False,
            "reason_codes": reasons,
            "report_hash": "0" * 64,
        }
    )
    return _hash_report(blocked)


def run_module(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    policy: RiskGatePolicy,
) -> IndependentRiskGateReport:
    if is_no_action(s5_bundle):
        return _no_action_report(risk_bundle, s5_bundle)
    report = evaluate_target(
        risk_bundle,
        target_paths(s5_bundle),
        policy,
        s5_bundle.payload.discrete_target.discrete_hash,
        s5_bundle.payload.discrete_target.validation.feasible,
    )
    if report.maximum_optimizer_risk_discrepancy > policy.maximum_optimizer_risk_discrepancy:
        return _block_on_discrepancy(report)
    return report
