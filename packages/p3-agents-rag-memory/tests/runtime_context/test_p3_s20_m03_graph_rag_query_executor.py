from __future__ import annotations
from importlib import import_module
from .s20_test_support import sample_payload
from quant_pipeline.phase_03_agents_rag_memory.s20.service import run_s20

def test_m03_operational():
    inputs, config = sample_payload()
    full = run_s20(inputs, config)
    module = import_module("quant_pipeline.phase_03_agents_rag_memory.modules.P3_S20_M03_graph_rag_query_executor")
    enriched = dict(inputs)
    enriched.update(config)
    for name in ("person_retrieval_query_panel","raw_retrieved_knowledge_bundle","graph_retrieval_bundle","person_learning_trajectory_bundle","retrieved_knowledge_bundle","retrieval_evidence_map","person_context_bundle","validated_person_context_bundle"):
        if hasattr(full, name): enriched[name] = getattr(full, name).model_dump(mode="json")
    payload = {name: enriched[name] for name in module.REQUIRED_INPUTS}
    result = module.run_module(payload, config)
    assert result["schema_version"]
