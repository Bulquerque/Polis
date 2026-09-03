from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import pytest
import yaml
ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "capabilities" / "products"
CONFIG = ROOT / "src" / "quant_pipeline" / "phase_03_agents_rag_memory" / "runtime_engine" / "assets" / "config" / "products"

def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))

@pytest.fixture(scope="session")
def plan_root() -> Path:
    return ROOT

@pytest.fixture
def execution_context() -> dict:
    return deepcopy(_load_json(FIXTURES / "s29" / "execution_context.json"))

@pytest.fixture
def m01_inputs() -> dict:
    return deepcopy(_load_json(FIXTURES / "s29" / "m01_valid_inputs.json"))

@pytest.fixture
def m02_inputs() -> dict:
    return deepcopy(_load_json(FIXTURES / "s29" / "m02_valid_inputs.json"))

@pytest.fixture
def s30_execution_context() -> dict:
    return deepcopy(_load_json(FIXTURES / "s30" / "execution_context.json"))

@pytest.fixture
def s30_upstream_inputs() -> dict:
    return deepcopy(_load_json(FIXTURES / "s30" / "upstream_inputs.json"))

@pytest.fixture
def s30_projection_config() -> dict:
    return deepcopy(_load_yaml(CONFIG / "S30_FEATURE_PROJECTION_CATALOG.yaml"))

@pytest.fixture
def s30_proposition_config() -> dict:
    return deepcopy(_load_yaml(CONFIG / "S30_PROPOSITION_REGISTRY.yaml"))

@pytest.fixture
def s30_products(s30_upstream_inputs, s30_execution_context, s30_projection_config, s30_proposition_config):
    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M01_social_feature_builder import run_module as m1
    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M02_context_memory_feature_builder import run_module as m2
    from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S30_M03_hypothesis_registry_builder import run_module as m3
    common = {"execution_context": s30_execution_context, "feature_projection_config": s30_projection_config}
    social = m1({"validated_society_state_panel": s30_upstream_inputs["validated_society_state_panel"], "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"], "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"]}, common)["outputs"]["social_feature_panel"]
    memory = m2({"next_memory_state": s30_upstream_inputs["next_memory_state"], "validated_society_state_panel": s30_upstream_inputs["validated_society_state_panel"], "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"]}, common)["outputs"]["context_memory_feature_panel"]
    hypotheses = m3({"social_feature_panel": social, "context_memory_feature_panel": memory, "evidence_tag_panel": s30_upstream_inputs["evidence_tag_panel"], "agent_disagreement_panel": s30_upstream_inputs["agent_disagreement_panel"], "proposition_registry_config": s30_proposition_config}, {"execution_context": s30_execution_context})["outputs"]["hypothesis_registry"]
    return {"social_feature_panel": social, "context_memory_feature_panel": memory, "hypothesis_registry": hypotheses}
