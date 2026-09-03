from .s20_test_support import sample_payload
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_s20

def test_s17_s18_s19_to_s20_contract_surface():
    inputs, config = sample_payload()
    result = run_s20(inputs, config)
    assert result.validated_person_context_bundle.records
    assert result.retrieval_evidence_map.records
