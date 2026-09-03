from __future__ import annotations
import pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.external_reference_guard import validate_external_references,ExternalReferenceLeakageError

def test_provider_document_tool_reference_leakage():
    cutoff='2026-07-27T12:00:00Z'
    assert validate_external_references(as_of_time=cutoff,provider_snapshots=[{'provider_id':'p','snapshot_available_at':'2026-07-27T10:00:00Z'}],document_refs=[{'document_id':'d','available_at':'2026-07-27T11:00:00Z'}],tool_results=[{'tool_call_id':'t','available_at':'2026-07-27T12:00:00Z'}])['status']=='PASS'
    cases=[
      dict(provider_snapshots=[{'provider_id':'p','snapshot_available_at':'2026-07-28T00:00:00Z'}],document_refs=[],tool_results=[]),
      dict(provider_snapshots=[],document_refs=[{'document_id':'d','available_at':'2026-07-28T00:00:00Z'}],tool_results=[]),
      dict(provider_snapshots=[],document_refs=[],tool_results=[{'tool_call_id':'t','available_at':'2026-07-28T00:00:00Z'}]),
    ]
    for case in cases:
      with pytest.raises(ExternalReferenceLeakageError,match='future'): validate_external_references(as_of_time=cutoff,**case)
