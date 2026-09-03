from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.execution_models import (
    PhaseName,
    ResourceBudget,
    TrialExecutionPlan,
    TrialSpec,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m03_backtest_runner import (
    PhaseRunnerRegistry,
    execute_trial_plan,
)

from tests.s03.conftest import FakePhaseRunner, valid_trade_handoff


def build_registry() -> PhaseRunnerRegistry:
    registry = PhaseRunnerRegistry()
    for phase in (PhaseName.P5, PhaseName.P6, PhaseName.P7):
        registry.register(phase, FakePhaseRunner(phase))
    registry.register(PhaseName.P8, FakePhaseRunner(PhaseName.P8, p8_handoff=valid_trade_handoff()))
    return registry


def test_operational_timestamps_do_not_change_semantic_trial_or_ledger_hash() -> None:
    plan = TrialExecutionPlan(
        plan_id="replay-plan",
        run_id="run-1",
        cycle_id="cycle-1",
        contract_pack_version="1.0.0",
        trials=(
            TrialSpec(
                trial_id="trial-1",
                configuration_id="config-1",
                configuration_sha256="a" * 64,
                fold_id="outer_000",
                seed_namespace="seed-v1",
            ),
        ),
        resource_budget=ResourceBudget(maximum_seconds=Decimal("10")),
    )
    first = execute_trial_plan(plan, build_registry())
    second = execute_trial_plan(plan, build_registry())
    assert first.bundles[0].bundle_sha256 == second.bundles[0].bundle_sha256
    assert first.content_sha256 == second.content_sha256
