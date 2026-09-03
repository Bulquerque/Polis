from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "runtime_engine"


@pytest.fixture
def load_fixture():
    def load(name: str):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return load
