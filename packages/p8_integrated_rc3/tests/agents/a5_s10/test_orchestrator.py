from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.orchestrator import run_audit_release

def test_end_to_end(orchestration_request):
    result=run_audit_release(orchestration_request)
    assert result.audit_report.overall_status.value=='PASS'
    assert result.qualification.eligible_for_p9_evaluation is True
    assert result.p9_handoff.qualification==result.qualification
    assert result.p9_handoff.production_promotion_allowed is False

def test_deterministic_ids(orchestration_request):
    a=run_audit_release(orchestration_request); b=run_audit_release(orchestration_request)
    assert a.audit_report.audit_id==b.audit_report.audit_id
    assert a.qualification.qualification_id==b.qualification.qualification_id
    assert a.p9_handoff.handoff_id==b.p9_handoff.handoff_id
