from datetime import timedelta
from pathlib import Path
import pytest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.errors import ReleaseIntegrityError
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_common import ArtifactRef, content_sha256
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_release import ReleaseEvidence, ReleasePublicationRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.release_publisher import publish_release

def evidence(**updates):
    base=dict(tests_passed=100,tests_failed=0,combined_coverage_percent=99.0,structure_gate_passed=True,
        clean_install_passed=True,clean_extraction_passed=True,deterministic_replay_passed=True,
        p9_consumer_passed=True,namespace_coexistence_passed=True)
    base.update(updates); return ReleaseEvidence(**base)

def request(tmp_path,context,dummy_qualification,p9_handoff,ref,**updates):
    (tmp_path/'a.txt').write_text('A',encoding='utf-8'); (tmp_path/'b.txt').write_text('B',encoding='utf-8')
    base=dict(context=context,package_name='pkg',package_version='0.1.0',release_root=str(tmp_path),
        included_paths=('a.txt','b.txt'),sealed_at=context.audit_time+timedelta(minutes=1),
        qualification=dummy_qualification,qualification_ref=ArtifactRef(artifact_id='q',content_sha256=content_sha256(dummy_qualification),schema_version='1.0.0',contract_version='1.0.0',producer_phase='P8',producer_module='P8.S10.M02'),p9_handoff=p9_handoff,p9_handoff_ref=ArtifactRef(artifact_id='p9',content_sha256=content_sha256(p9_handoff),schema_version='1.0.0',contract_version='1.0.0',producer_phase='P8',producer_module='P8.S10.M03'),
        evidence=evidence(),known_debts=('none',),dependency_components=('pydantic',))
    base.update(updates); return ReleasePublicationRequest(**base)

def test_release_manifest_deterministic(tmp_path,context,dummy_qualification,p9_handoff,ref):
    req=request(tmp_path,context,dummy_qualification,p9_handoff,ref)
    a=publish_release(req); b=publish_release(req)
    assert a==b; assert len(a.manifest.files)==2
    assert a.p0_handoff.production_promotion_allowed is False

def test_outside_root_rejected(tmp_path,context,dummy_qualification,p9_handoff,ref):
    req=request(tmp_path,context,dummy_qualification,p9_handoff,ref,included_paths=('../outside.txt',))
    with pytest.raises(ReleaseIntegrityError): publish_release(req)

def test_duplicate_path_rejected(tmp_path,context,dummy_qualification,p9_handoff,ref):
    req=request(tmp_path,context,dummy_qualification,p9_handoff,ref,included_paths=('a.txt','a.txt'))
    with pytest.raises(ReleaseIntegrityError): publish_release(req)

def test_missing_file_rejected(tmp_path,context,dummy_qualification,p9_handoff,ref):
    req=request(tmp_path,context,dummy_qualification,p9_handoff,ref,included_paths=('missing.txt',))
    with pytest.raises(ReleaseIntegrityError): publish_release(req)

@pytest.mark.parametrize('field,value',[
 ('tests_failed',1),('structure_gate_passed',False),('clean_install_passed',False),
 ('clean_extraction_passed',False),('deterministic_replay_passed',False),
 ('p9_consumer_passed',False),('namespace_coexistence_passed',False),
])
def test_incomplete_evidence_blocks_release(tmp_path,context,dummy_qualification,p9_handoff,ref,field,value):
    req=request(tmp_path,context,dummy_qualification,p9_handoff,ref,evidence=evidence(**{field:value}))
    with pytest.raises(ReleaseIntegrityError): publish_release(req)
