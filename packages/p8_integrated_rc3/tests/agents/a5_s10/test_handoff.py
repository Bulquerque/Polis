from datetime import timedelta
import pytest
from pydantic import ValidationError
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.errors import ContractIntegrityError
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_handoff import OutcomeEvidenceRecord, P9HandoffRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import EvidenceClass, OutcomeMaturityHint
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.p9_handoff_builder import build_p9_handoff

def test_valid_handoff(p9_template):
    result=build_p9_handoff(p9_template)
    assert result.all_candidate_ids==('c1','c2')
    assert result.production_promotion_allowed is False

def test_missing_evidence_rejected(p9_template):
    bad=p9_template.model_copy(update={'evidence_records':p9_template.evidence_records[:1]})
    with pytest.raises(ContractIntegrityError): build_p9_handoff(bad)

def test_duplicate_candidate_ids_rejected(p9_template):
    bad=p9_template.model_copy(update={'all_candidate_ids':('c1','c1')})
    with pytest.raises(ContractIntegrityError): build_p9_handoff(bad)

def test_missing_lineage_rejected(p9_template):
    bad=p9_template.model_copy(update={'lineage_records':p9_template.lineage_records[:1]})
    with pytest.raises(ContractIntegrityError): build_p9_handoff(bad)

def test_late_commitment_rejected(p9_template):
    ec=p9_template.evaluation_commitment.model_copy(update={'committed_at':p9_template.context.decision_time+timedelta(seconds=1)})
    data=p9_template.model_dump(); data['evaluation_commitment']=ec
    with pytest.raises(ValidationError): P9HandoffRequest(**data)

def test_factual_execution_requires_ref(p9_template):
    with pytest.raises(ValidationError):
        OutcomeEvidenceRecord(evidence_id='x',candidate_id='c1',evidence_class=EvidenceClass.FACTUAL_EXECUTED,
            maturity_hint=OutcomeMaturityHint.EXPECTED_MATURED,artifact_refs=())

def test_model_counterfactual_semantics(p9_template):
    with pytest.raises(ValidationError):
        OutcomeEvidenceRecord(evidence_id='x',candidate_id='c1',evidence_class=EvidenceClass.MODEL_BASED_COUNTERFACTUAL,
            maturity_hint=OutcomeMaturityHint.EXPECTED_MATURED,artifact_refs=())
