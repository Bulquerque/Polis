from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_05_underlying_forecasts import ExecutionMode, PhaseRunner
from quant_pipeline.phase_05_underlying_forecasts.domain.core import ModuleAction, ModuleRequest, ModuleStatus
from tests.fixtures import build_fixture
from tests.test_full_pipeline import _context


def test_s1_m03_empty_optional_lineage_degrades_explicitly(tmp_path: Path) -> None:
    fixture = build_fixture()
    context = _context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)
    result = PhaseRunner(context).run((ModuleRequest(module_id="P5.S1.M03", action=ModuleAction.RUN),))
    module = result.results[0]
    assert module.status is ModuleStatus.DEGRADED
    assert not module.errors
    for name in ("p5_hypothesis_confirmation_registry", "p4_perspective_context"):
        value = context.artifact_store.read(module.outputs[name])
        assert value["availability"] == "UNAVAILABLE"
        assert value["records"] == []


def test_unknown_module_is_contained_as_rejected_result(tmp_path: Path) -> None:
    fixture = build_fixture()
    context = _context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)
    result = PhaseRunner(context).run((ModuleRequest(module_id="P5.S9.M99", action=ModuleAction.RUN),))
    module = result.results[0]
    assert module.status is ModuleStatus.REJECTED
    assert module.errors[0].code == "P5-MODULE-UNKNOWN"
