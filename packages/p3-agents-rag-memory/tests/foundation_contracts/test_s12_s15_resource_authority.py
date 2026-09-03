from __future__ import annotations
import copy,yaml,pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.authority import rag_signature,validate_incremental_rebuild,validate_temporal_graph_record,validate_tool_schema_lock,resolve_entitlement,ResourceAuthorityError

def y(p): return yaml.safe_load(p.read_text(encoding='utf-8'))

def test_rag_signature_seals_all_reproducibility_fields(root):
    cfg=y(root/'config/resources/s12/rag_index_authority.yaml')
    sig=rag_signature(cfg,embedding_provider_id='fixture',embedding_model_id='embed-v1',embedding_model_version='1.0.0',embedding_dimension=8)
    required=set(cfg['incremental_rebuild']['compatibility_fields'])
    assert required <= set(sig)
    assert validate_incremental_rebuild(sig,copy.deepcopy(sig),list(required))['status']=='PASS'
    changed=copy.deepcopy(sig); changed['embedding_model_version']='2.0.0'
    with pytest.raises(ResourceAuthorityError,match='incompatible'): validate_incremental_rebuild(sig,changed,list(required))

def test_temporal_graph_ontology_is_fail_closed(root):
    ontology=y(root/'config/resources/s13/TEMPORAL_GRAPH_ONTOLOGY.yaml')
    row={'node_type':'event','effective_from':'2026-01-01T00:00:00Z','effective_to':None,'available_at':'2026-01-02T00:00:00Z','ingested_at':'2026-01-02T01:00:00Z'}
    assert validate_temporal_graph_record(row,ontology,as_of_time='2026-01-03T00:00:00Z')['status']=='PASS'
    future=copy.deepcopy(row); future['available_at']='2026-02-01T00:00:00Z'
    with pytest.raises(ResourceAuthorityError,match='future'): validate_temporal_graph_record(future,ontology,as_of_time='2026-01-03T00:00:00Z')

def test_memory_policy_is_versioned_and_single_writer(root):
    auth=y(root/'config/warmup_memory/MEMORY_POLICY_AUTHORITY.yaml')
    assert set(auth['policy_dimensions'])=={'scope','retention','visibility','budget','redaction'}
    assert auth['concurrent_refresh_policy']=='SINGLE_WRITER_COMPARE_AND_SWAP'

def test_tool_schema_lock_deny_revocation_conflict(root):
    registry=y(root/'config/resources/s15/tool_registry_config.yaml'); lock=y(root/'config/resources/s15/TOOL_SCHEMA_LOCK.yaml')
    assert validate_tool_schema_lock(registry,lock)['status']=='PASS'
    assert resolve_entitlement(allow_rules=[],deny_rules=[],revoked=False)=='DENY'
    assert resolve_entitlement(allow_rules=['allow'],deny_rules=['deny'],revoked=False)=='DENY'
    assert resolve_entitlement(allow_rules=['allow'],deny_rules=[],revoked=True)=='DENY'
    assert resolve_entitlement(allow_rules=['allow'],deny_rules=[],revoked=False)=='ALLOW'
