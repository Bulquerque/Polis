from __future__ import annotations
import copy, json, yaml
from pathlib import Path
import pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.governance.schema_registry import SchemaRegistry
from quant_pipeline.phase_03_agents_rag_memory.foundation.governance.handoff import validate_phase2_handoff
from quant_pipeline.phase_03_agents_rag_memory.foundation.governance.quality import apply_source_quality_policy
from quant_pipeline.phase_03_agents_rag_memory.foundation.temporal_authority.errors import S2ContractError
from quant_pipeline.phase_03_agents_rag_memory.foundation.learning_feedback.errors import S3ContractError
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M01_point_in_time_context_gate import run_module as pit
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S3_M02_matured_belief_feedback_ingestor import run_module as feedback

class Resolver:
 def __init__(self,p): self.p=p
 def resolve(self,r): return self.p[str(r["artifact_name"])]
class CommitmentResolver:
 def __init__(self,row): self.row=row
 def resolve(self,cid): assert cid==self.row["commitment_id"]; return self.row

def payload(root): return json.loads((root/'fixtures/external_compat/p2_real_packager_fixture.json').read_text())

def test_global_schema_authority_is_used(root,tmp_path):
    global_root=tmp_path/'schemas'; global_root.mkdir()
    for name in ['clean_context_source_panel','clean_document_panel','clean_event_reference_panel','source_quality_panel','context_handoff_manifest','phase3_handoff_manifest']:
        (global_root/f'{name}.schema.yaml').write_bytes((root/'schemas'/f'{name}.schema.yaml').read_bytes())
    out=validate_phase2_handoff(payload(root),{'global_schema_root':str(global_root)})
    assert out['schema_authority']['mode']=='GLOBAL_REPOSITORY'
    assert len(out['schema_authority']['records'])==6
    assert all(r['schema_authority']=='GLOBAL_REPOSITORY' for r in out['artifacts'])

def test_qualification_event_requires_effective_time(root,governance_outputs):
    p=payload(root)
    handoff=validate_phase2_handoff(p)
    policy=yaml.safe_load((root/'config/governance/SOURCE_QUALITY_POLICY.yaml').read_text())
    validated=apply_source_quality_policy({'validated_phase2_handoff':handoff,'source_quality_panel':p['source_quality_panel'],'source_quality_policy_config':policy})
    with pytest.raises(S2ContractError,match='EFFECTIVE_TIME_MISSING'):
      pit({'validated_context_inputs':validated,'evaluation_window_config':{'as_of_time':'2026-07-27T12:00:00Z','timezone':'UTC','boundary_rule':'available_at_equal_as_of_allowed'}},{'artifact_resolver':Resolver(p),'strict_artifact_hashes':False,'execution_profile':'QUALIFICATION'})

def test_as_of_alias_mismatch_fails(root):
    p=payload(root)
    handoff=validate_phase2_handoff(p)
    policy=yaml.safe_load((root/'config/governance/SOURCE_QUALITY_POLICY.yaml').read_text())
    validated=apply_source_quality_policy({'validated_phase2_handoff':handoff,'source_quality_panel':p['source_quality_panel'],'source_quality_policy_config':policy})
    with pytest.raises(S2ContractError,match='AS_OF_ALIAS_MISMATCH'):
      pit({'validated_context_inputs':validated,'evaluation_window_config':{'as_of':'2026-07-27T12:00:00Z','as_of_time':'2026-07-28T12:00:00Z','timezone':'UTC'}},{'artifact_resolver':Resolver(p)})

def test_commitment_matching_qualification(root,governance_outputs):
    snapshot=copy.deepcopy(governance_outputs['phase3_run_snapshot']); h='a'*64
    item={'feedback_id':'f1','commitment_id':'c1','commit_hash':h,'expected_commit_hash':h,'person_id':'p1','proposition_id':'prop1','horizon':'1d','source_cycle_id':1,'matures_at':'2026-07-26T00:00:00Z','outcome_available_at':'2026-07-26T01:00:00Z','experience_available_from_cycle':2,'original_belief_ref':{'person_id':'p1','proposition_id':'prop1','horizon':'1d'},'outcome_ref':{'person_id':'p1','proposition_id':'prop1','horizon':'1d'},'evaluation_summary':{},'lineage_id':'lin'}
    package={'schema_version':'v14.1-rc4.1','contract_version':'p9.p3.belief_outcome_feedback.v1','artifact_id':'pkg','created_at':'2026-07-26T02:00:00Z','lineage_id':'same','status':'ACTIVE','feedback_items':[item]}
    manifest={'schema_version':'v14.1-rc4.1','contract_version':'p9.p3.learning_feedback_handoff.v1','artifact_id':'man','created_at':'2026-07-26T02:00:00Z','lineage_id':'same','status':'ACTIVE','feedback_artifact_id':'pkg'}
    commitment={'commitment_id':'c1','commit_hash':h,'person_id':'p1','proposition_id':'prop1','horizon':'1d'}
    out=feedback({'p9_belief_outcome_feedback_package':package,'phase3_learning_feedback_handoff_manifest':manifest,'phase3_run_snapshot':snapshot},{'current_cycle_id':2,'processed_at':'2026-07-27T12:00:00Z','package_root':root,'execution_profile':'QUALIFICATION','commitment_resolver':CommitmentResolver(commitment)})['outputs']['active_belief_feedback_bundle']
    assert out['feedback_items'][0]['commitment_match_status']=='VERIFIED'

def test_commitment_mismatch_fails(root,governance_outputs):
    snapshot=copy.deepcopy(governance_outputs['phase3_run_snapshot']); h='a'*64
    item={'feedback_id':'f1','commitment_id':'c1','commit_hash':h,'expected_commit_hash':h,'person_id':'p1','proposition_id':'prop1','horizon':'1d','source_cycle_id':1,'matures_at':'2026-07-26T00:00:00Z','outcome_available_at':'2026-07-26T01:00:00Z','experience_available_from_cycle':2,'original_belief_ref':{'person_id':'p1','proposition_id':'prop1','horizon':'1d'},'outcome_ref':{'person_id':'p1','proposition_id':'prop1','horizon':'1d'},'evaluation_summary':{},'lineage_id':'lin'}
    package={'schema_version':'v14.1-rc4.1','contract_version':'p9.p3.belief_outcome_feedback.v1','artifact_id':'pkg','created_at':'2026-07-26T02:00:00Z','lineage_id':'same','status':'ACTIVE','feedback_items':[item]}
    manifest={'schema_version':'v14.1-rc4.1','contract_version':'p9.p3.learning_feedback_handoff.v1','artifact_id':'man','created_at':'2026-07-26T02:00:00Z','lineage_id':'same','status':'ACTIVE','feedback_artifact_id':'pkg'}
    bad={'commitment_id':'c1','commit_hash':'b'*64,'person_id':'p1','proposition_id':'prop1','horizon':'1d'}
    with pytest.raises(S3ContractError,match='COMMITMENT_MATCH_FAILED'):
      feedback({'p9_belief_outcome_feedback_package':package,'phase3_learning_feedback_handoff_manifest':manifest,'phase3_run_snapshot':snapshot},{'current_cycle_id':2,'processed_at':'2026-07-27T12:00:00Z','package_root':root,'execution_profile':'QUALIFICATION','commitment_resolver':CommitmentResolver(bad)})


class FakeCanaryProbe:
    def __init__(self,response): self.response=response
    def probe(self,*,provider_id,model_id,prompt): return self.response

def test_executable_knowledge_canary_pass_and_detect(root):
    from quant_pipeline.phase_03_agents_rag_memory.foundation.temporal_authority.canary import run_canary_suite
    suite=yaml.safe_load((root/'config/governance/KNOWLEDGE_CANARIES.yaml').read_text())
    clean=run_canary_suite('p','m',suite,FakeCanaryProbe('UNKNOWN'))
    assert clean['status']=='PASS'
    contaminated=run_canary_suite('p','m',suite,FakeCanaryProbe('P3_FUTURE_CANARY_ALPHA'))
    assert contaminated['status']=='DETECTED'
