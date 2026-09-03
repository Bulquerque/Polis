from decimal import Decimal
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import (
    CycleTerminalState, ImplementationRobustness, StatisticalQualification, TechnicalValidity)
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.independent_auditor import run_independent_audit
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_qualification import QualificationRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.qualification_gate import run_qualification_gate

def make(bundle,robustness,statistical,state=CycleTerminalState.EXECUTED_VALID):
    return QualificationRequest(context=bundle.context,terminal_state=state,audit_report=run_independent_audit(bundle),
        robustness=robustness,statistical=statistical)

def test_qualified_path(bundle,robustness,statistical):
    result=run_qualification_gate(make(bundle,robustness,statistical))
    assert result.technical_validity==TechnicalValidity.PASS
    assert result.implementation_robustness==ImplementationRobustness.PASS
    assert result.statistical_qualification==StatisticalQualification.QUALIFIED
    assert result.eligible_for_p9_evaluation is True
    assert result.production_promotion_allowed is False

def test_no_action_statistical_not_applicable(bundle,robustness,statistical):
    result=run_qualification_gate(make(bundle,robustness,statistical,CycleTerminalState.NO_ACTION_VALID))
    assert result.statistical_qualification==StatisticalQualification.NOT_APPLICABLE

def test_bad_audit_fails_technical(bundle,robustness,statistical):
    bad=bundle.model_copy(update={'expected_candidate_ids':('x',)})
    result=run_qualification_gate(make(bad,robustness,statistical))
    assert result.technical_validity==TechnicalValidity.FAIL
    assert result.eligible_for_p9_evaluation is False

def test_missing_robustness_is_insufficient(bundle,robustness,statistical):
    bad=robustness.model_copy(update={'golden_threads_required':(), 'perturbations_required':0,'perturbations_passed':0})
    result=run_qualification_gate(make(bundle,bad,statistical))
    assert result.implementation_robustness==ImplementationRobustness.INSUFFICIENT_EVIDENCE

def test_failed_robustness(bundle,robustness,statistical):
    bad=robustness.model_copy(update={'clean_replay_passed':False})
    assert run_qualification_gate(make(bundle,bad,statistical)).implementation_robustness==ImplementationRobustness.FAIL

def test_statistical_evidence_requirements(bundle,robustness,statistical):
    incomplete=statistical.model_copy(update={'trial_registry_complete':False,'holdout_preserved':False,'returns':(Decimal('0.1'),)})
    result=run_qualification_gate(make(bundle,robustness,incomplete))
    assert result.statistical_qualification==StatisticalQualification.INSUFFICIENT_EVIDENCE
    assert len(result.reason_codes)>=3

def test_dsr_and_pbo_can_fail(bundle,robustness,statistical):
    strict=statistical.model_copy(update={'returns':tuple(Decimal(str(x)) for x in [-0.01,-0.012,-0.008,-0.011,-0.009]*8), 'trial_sharpes':(Decimal('2'),Decimal('3')), 'dsr_threshold':Decimal('0.95'),'pbo_threshold':Decimal('0')})
    result=run_qualification_gate(make(bundle,robustness,strict))
    assert result.statistical_qualification==StatisticalQualification.FAILED
