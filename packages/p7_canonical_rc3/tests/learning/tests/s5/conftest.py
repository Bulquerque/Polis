from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def input_bundle():
    return copy.deepcopy(json.loads((ROOT / "fixtures/integration/s5_input_bundle.json").read_text()))

@pytest.fixture
def config():
    return copy.deepcopy(yaml.safe_load((ROOT / "configs/s5_default_config.yaml").read_text()))
