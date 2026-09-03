from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S29_M01_agent_disagreement_panel_builder import (
    run_module as run_m01,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S29_M02_evidence_claim_extractor import (
    run_module as run_m02,
)


def test_complete_subphase_materializes_both_outputs(
    m01_inputs: dict,
    m02_inputs: dict,
    execution_context: dict,
) -> None:
    disagreement = run_m01(m01_inputs, execution_context)["outputs"]
    evidence = run_m02(m02_inputs, execution_context)["outputs"]
    assert set(disagreement) == {"agent_disagreement_panel"}
    assert set(evidence) == {"evidence_tag_panel"}
    assert disagreement["agent_disagreement_panel"]["run_id"] == execution_context["run_id"]
    assert evidence["evidence_tag_panel"]["run_id"] == execution_context["run_id"]


def test_subphase_has_no_external_provider_path() -> None:
    import quant_pipeline.phase_03_agents_rag_memory.s29_products as products

    source = open(products.__file__, encoding="utf-8").read()
    forbidden_imports = ("httpx", "requests", "openai", "mcp", "langchain", "llama_index")
    assert not any(f"import {name}" in source or f"from {name}" in source for name in forbidden_imports)
