from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parents[1]
SRC = ROOT / "src"
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# P3 is the regular shared ``quant_pipeline`` package.  When another phase
# was imported first during root collection, extend the already-loaded package
# explicitly so P3 tests resolve their own modules as well.
import quant_pipeline

P3_NAMESPACE = str(SRC / "quant_pipeline")
if P3_NAMESPACE not in quant_pipeline.__path__:
    quant_pipeline.__path__.append(P3_NAMESPACE)

# P3 keeps its qualification helpers under a package-local ``tools`` tree,
# while the workspace also has a root-level namespace with the same name.
# Extend both namespace packages explicitly so root collection cannot hide the
# package-local helpers or the phase-specific test support modules.
import tools

P3_TOOLS = str(ROOT / "tools")
if hasattr(tools, "__path__") and P3_TOOLS not in tools.__path__:
    tools.__path__.append(P3_TOOLS)

import tests as all_tests

P3_TESTS = str(ROOT / "tests")
if hasattr(all_tests, "__path__") and P3_TESTS not in all_tests.__path__:
    all_tests.__path__.append(P3_TESTS)


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def governance_outputs(root: Path) -> dict[str, object]:
    return _load_json(root / "fixtures/integration/governance_outputs.json")


@pytest.fixture(scope="session")
def population_outputs(root: Path) -> dict[str, object]:
    return _load_json(root / "fixtures/integration/population_outputs.json")


@pytest.fixture(scope="session")
def resource_outputs(root: Path) -> dict[str, object]:
    return _load_json(root / "fixtures/integration/resource_outputs.json")


@pytest.fixture(scope="session")
def operational_policy(root: Path) -> dict[str, object]:
    return yaml.safe_load((root / "config/population/operational_person_policy.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def objective_aliases(root: Path) -> dict[str, object]:
    return yaml.safe_load((root / "config/population/objective_aliases.yaml").read_text(encoding="utf-8"))
