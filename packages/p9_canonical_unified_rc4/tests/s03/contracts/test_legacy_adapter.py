from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.adapters.legacy_phase_runner import (
    LegacyRunPhaseAdapter,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import TerminalStatus
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.execution_models import (
    PhaseName,
    PhaseRunRequest,
    ResourceBudget,
    RunnerCapability,
    phase_run_result_sha256,
)


def request(phase: PhaseName) -> PhaseRunRequest:
    return PhaseRunRequest(
        phase=phase,
        run_id="run",
        cycle_id="cycle",
        trial_id="trial",
        fold_id="fold",
        configuration_id="config",
        configuration_sha256="a" * 64,
        seed=1,
        input_artifacts=(),
        resource_budget=ResourceBudget(maximum_seconds=Decimal("5")),
    )


def test_legacy_p5_is_explicitly_research_only_and_hash_valid() -> None:
    adapter = LegacyRunPhaseAdapter(PhaseName.P5, lambda inputs, config: {"ok": True})
    result = adapter.run(request(PhaseName.P5))
    assert adapter.capability is RunnerCapability.LEGACY_RESEARCH_ONLY
    assert result.status is TerminalStatus.SUCCESS
    assert result.output_artifacts[0].availability == "LEGACY_RESEARCH_ONLY"
    assert phase_run_result_sha256(result) == result.result_sha256


def test_legacy_p8_cannot_be_production_qualified() -> None:
    adapter = LegacyRunPhaseAdapter(PhaseName.P8, lambda inputs, config: {"ok": True})
    result = adapter.run(request(PhaseName.P8))
    assert result.status is TerminalStatus.CAPABILITY_UNAVAILABLE
    assert result.p8_handoff is None
    assert "P9_S3_LEGACY_P8_NOT_QUALIFIABLE" in result.reason_codes
