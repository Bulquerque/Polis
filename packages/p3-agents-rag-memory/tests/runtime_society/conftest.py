from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any
import pytest
import yaml
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
FIXTURES = ROOT / "fixtures" / "capabilities" / "society"
CONFIG = ROOT / "src" / "quant_pipeline" / "phase_03_agents_rag_memory" / "runtime_engine" / "assets" / "config" / "society"

def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value

@pytest.fixture
def valid_fixture():
    return lambda name: load_json(FIXTURES / "valid" / name)

@pytest.fixture
def invalid_fixture():
    return lambda name: load_json(FIXTURES / "invalid" / name)

@pytest.fixture
def config_fixture():
    return lambda name: load_yaml(CONFIG / name)

@pytest.fixture(scope="session")
def plan_root() -> Path:
    return ROOT
