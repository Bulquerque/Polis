from quant_pipeline.phase_03_agents_rag_memory.orchestration.registry import MODULE_REGISTRY
from quant_pipeline.phase_03_agents_rag_memory.orchestration.validator import validate_registry

def test_exact_81_modules():
    assert len(MODULE_REGISTRY)==81
    assert len({x.module_id for x in MODULE_REGISTRY})==81
    assert validate_registry()==[]

def test_no_legacy_namespaces(root):
    from quant_pipeline.phase_03_agents_rag_memory.orchestration.validator import validate_source_tree
    assert validate_source_tree(root/'src')==[]
