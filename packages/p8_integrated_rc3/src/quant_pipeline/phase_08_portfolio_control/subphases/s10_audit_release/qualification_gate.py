from __future__ import annotations
import hashlib
from .enums import (AuditOverallStatus, CycleTerminalState, ImplementationRobustness,
    ReasonCode, StatisticalQualification, TechnicalValidity)
from .models_qualification import QualificationDecision, QualificationRequest
from .statistical_readiness import build_diagnostics

def _qualification_id(request: QualificationRequest) -> str:
    raw = f"{request.context.run_id}|{request.context.cycle_id}|{request.audit_report.audit_id}"
    return "qua_" + hashlib.sha256(raw.encode()).hexdigest()[:20]

def _technical(request: QualificationRequest) -> tuple[TechnicalValidity, list[ReasonCode]]:
    if request.audit_report.overall_status == AuditOverallStatus.FAIL:
        return TechnicalValidity.FAIL, [ReasonCode.TECHNICAL_AUDIT_FAILED]
    return TechnicalValidity.PASS, []

def _robustness(request: QualificationRequest) -> tuple[ImplementationRobustness, list[ReasonCode]]:
    item = request.robustness
    complete = bool(item.golden_threads_required) and item.perturbations_required > 0
    if not complete:
        return ImplementationRobustness.INSUFFICIENT_EVIDENCE, [ReasonCode.ROBUSTNESS_EVIDENCE_MISSING]
    passed = (item.clean_replay_passed and item.clean_install_passed and item.clean_extraction_passed
              and item.consumer_contracts_passed
              and set(item.golden_threads_required) <= set(item.golden_threads_passed)
              and item.perturbations_passed == item.perturbations_required)
    if not passed:
        return ImplementationRobustness.FAIL, [ReasonCode.ROBUSTNESS_TEST_FAILED]
    return ImplementationRobustness.PASS, []

def _statistical(request: QualificationRequest):
    evidence = request.statistical
    diagnostics = build_diagnostics(evidence)
    if request.terminal_state == CycleTerminalState.NO_ACTION_VALID:
        return StatisticalQualification.NOT_APPLICABLE, diagnostics, []
    reasons: list[ReasonCode] = []
    if not evidence.trial_registry_complete:
        reasons.append(ReasonCode.TRIAL_REGISTRY_INCOMPLETE)
    if not evidence.holdout_preserved:
        reasons.append(ReasonCode.HOLDOUT_VIOLATED)
    if diagnostics.observation_count < evidence.minimum_observations:
        reasons.append(ReasonCode.STATISTICAL_SAMPLE_INSUFFICIENT)
    if reasons:
        return StatisticalQualification.INSUFFICIENT_EVIDENCE, diagnostics, reasons
    if diagnostics.deflated_sharpe_ratio is not None and diagnostics.deflated_sharpe_ratio < evidence.dsr_threshold:
        reasons.append(ReasonCode.DSR_BELOW_THRESHOLD)
    if diagnostics.probability_backtest_overfitting is not None and diagnostics.probability_backtest_overfitting > evidence.pbo_threshold:
        reasons.append(ReasonCode.PBO_ABOVE_THRESHOLD)
    status = StatisticalQualification.FAILED if reasons else StatisticalQualification.QUALIFIED
    return status, diagnostics, reasons

def run_qualification_gate(request: QualificationRequest) -> QualificationDecision:
    technical, tech_reasons = _technical(request)
    robust, robust_reasons = _robustness(request)
    statistical, diagnostics, stat_reasons = _statistical(request)
    reasons = tuple(tech_reasons + robust_reasons + stat_reasons)
    eligible = technical == TechnicalValidity.PASS and robust == ImplementationRobustness.PASS
    return QualificationDecision(qualification_id=_qualification_id(request), context=request.context,
        terminal_state=request.terminal_state, technical_validity=technical,
        implementation_robustness=robust, statistical_qualification=statistical,
        diagnostics=diagnostics, reason_codes=reasons, eligible_for_p9_evaluation=eligible,
        production_promotion_allowed=False)
