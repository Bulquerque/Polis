from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_vertical_fixture_s1_to_s2() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_vertical_fixture.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    output = json.loads(completed.stdout)
    assert output["s1_status"] == "SUCCESS"
    assert output["s2_status"] == "SUCCESS"
    assert output["s1_module_count"] == 6
    assert output["s2_module_count"] == 6
    assert output["configuration_count"] > 0
    assert output["trial_slot_count"] > 0


def test_namespace_root_is_not_regular_package() -> None:
    assert not (ROOT / "src" / "quant_pipeline" / "__init__.py").exists()


def test_both_schema_resources_are_available() -> None:
    from quant_pipeline.phase_09.contracts.schema_resources import list_schema_names as s1_names
    from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.schema_resources import list_schema_names as s2_names

    assert len(s1_names()) >= 70
    assert len(s2_names()) >= 70
