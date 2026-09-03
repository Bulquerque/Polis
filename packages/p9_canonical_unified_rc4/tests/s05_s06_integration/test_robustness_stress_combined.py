from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_pipeline.phase_09.orchestration.robustness_stress import RobustnessStressRunRequest, run_robustness_stress
from quant_pipeline.phase_09.orchestration.robustness_stress.contracts import RobustnessStressOutputBundle
from quant_pipeline.phase_09.orchestration.robustness_stress.schema_export import export_schemas


EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "s05_s06" / "combined"


def test_combined_runner_is_deterministic() -> None:
    request = RobustnessStressRunRequest.model_validate_json(
        (EXAMPLES / "robustness_stress_request.json").read_text(encoding="utf-8")
    )
    first = run_robustness_stress(request)
    second = run_robustness_stress(request)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.manifest.s5_bundle_sha256 == first.s5.bundle_sha256
    assert first.manifest.s6_bundle_sha256 == first.s6.bundle_sha256
    assert first.s5_reference.bundle_sha256 == first.s5.bundle_sha256


def test_combined_output_matches_frozen_fixture() -> None:
    request = RobustnessStressRunRequest.model_validate_json(
        (EXAMPLES / "robustness_stress_request.json").read_text(encoding="utf-8")
    )
    observed = run_robustness_stress(request).model_dump(mode="json")
    expected = RobustnessStressOutputBundle.model_validate_json(
        (EXAMPLES / "robustness_stress_output.json").read_text(encoding="utf-8")
    ).model_dump(mode="json")
    assert observed == expected


def test_mismatched_context_is_rejected() -> None:
    raw = json.loads((EXAMPLES / "robustness_stress_request.json").read_text(encoding="utf-8"))
    raw["s6"]["scenario_registry"]["context"]["run_id"] = "other-run"
    with pytest.raises(ValueError, match="same RunContext"):
        RobustnessStressRunRequest.model_validate_json(json.dumps(raw))


def test_integrated_schema_export(tmp_path: Path) -> None:
    paths = export_schemas(tmp_path)
    assert {path.name for path in paths} == {
        "RobustnessStressRunRequest.schema.json",
        "RobustnessStressOutputBundle.schema.json",
    }
    for path in paths:
        assert json.loads(path.read_text(encoding="utf-8"))["type"] == "object"
