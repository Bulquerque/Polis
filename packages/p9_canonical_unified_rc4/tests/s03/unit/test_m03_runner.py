from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import TerminalStatus
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.execution_models import (
    ExecutionMode,
    PhaseName,
    ResourceBudget,
    RunnerCapability,
    TrialExecutionPlan,
    TrialSpec,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m03_backtest_runner import (
    PhaseRunnerRegistry,
    execute_trial_plan,
)

from tests.s03.conftest import FakePhaseRunner, ZERO_HASH, valid_trade_handoff


def plan(*, mode=ExecutionMode.FULL_PIPELINE, fixed=None, max_artifacts=128):
    return TrialExecutionPlan(
        plan_id="trial-plan-1",
        run_id="run-1",
        cycle_id="cycle-1",
        contract_pack_version="1.0.0",
        trials=(
            TrialSpec(
                trial_id="trial-1",
                configuration_id="config-1",
                configuration_sha256=ZERO_HASH,
                fold_id="outer_000",
                seed_namespace="seed-space",
                mode=mode,
                fixed_p8_handoff=fixed,
            ),
        ),
        resource_budget=ResourceBudget(
            maximum_seconds=Decimal("100"),
            maximum_output_artifacts=max_artifacts,
        ),
    )


def full_registry(handoff=None):
    registry = PhaseRunnerRegistry()
    runners = {}
    for phase in PhaseName:
        runner = FakePhaseRunner(phase, p8_handoff=handoff if phase is PhaseName.P8 else None)
        registry.register(phase, runner)
        runners[phase] = runner
    return registry, runners


def test_executes_phases_in_canonical_order_and_threads_artifacts():
    registry, runners = full_registry(valid_trade_handoff())
    ledger = execute_trial_plan(plan(), registry)
    bundle = ledger.bundles[0]
    assert [result.phase for result in bundle.phase_results] == list(PhaseName)
    assert bundle.status is TerminalStatus.SUCCESS
    assert runners[PhaseName.P6].requests[0].input_artifacts == bundle.phase_results[0].output_artifacts
    assert runners[PhaseName.P8].requests[0].input_artifacts == bundle.phase_results[2].output_artifacts


def test_seeds_are_stable_across_repeated_execution():
    registry_a, runners_a = full_registry(valid_trade_handoff())
    registry_b, runners_b = full_registry(valid_trade_handoff())
    execute_trial_plan(plan(), registry_a)
    execute_trial_plan(plan(), registry_b)
    assert [runners_a[p].requests[0].seed for p in PhaseName] == [runners_b[p].requests[0].seed for p in PhaseName]
    assert len(set(runners_a[p].requests[0].seed for p in PhaseName)) == 4


def test_stops_after_phase_failure_and_preserves_terminal_state():
    registry = PhaseRunnerRegistry()
    registry.register(PhaseName.P5, FakePhaseRunner(PhaseName.P5))
    registry.register(PhaseName.P6, FakePhaseRunner(PhaseName.P6, status=TerminalStatus.FAILED))
    registry.register(PhaseName.P7, FakePhaseRunner(PhaseName.P7))
    registry.register(PhaseName.P8, FakePhaseRunner(PhaseName.P8, p8_handoff=valid_trade_handoff()))
    bundle = execute_trial_plan(plan(), registry).bundles[0]
    assert [result.phase for result in bundle.phase_results] == [PhaseName.P5, PhaseName.P6]
    assert bundle.status is TerminalStatus.FAILED


def test_missing_runner_returns_capability_unavailable():
    registry = PhaseRunnerRegistry()
    registry.register(PhaseName.P5, FakePhaseRunner(PhaseName.P5))
    bundle = execute_trial_plan(plan(), registry).bundles[0]
    assert bundle.status is TerminalStatus.CAPABILITY_UNAVAILABLE
    assert "P9_S3_PHASE_CAPABILITY_UNAVAILABLE" in bundle.reason_codes


def test_legacy_p8_cannot_be_successful_without_typed_handoff():
    registry = PhaseRunnerRegistry()
    for phase in (PhaseName.P5, PhaseName.P6, PhaseName.P7):
        registry.register(phase, FakePhaseRunner(phase))
    registry.register(
        PhaseName.P8,
        FakePhaseRunner(
            PhaseName.P8,
            status=TerminalStatus.CAPABILITY_UNAVAILABLE,
            capability=RunnerCapability.LEGACY_RESEARCH_ONLY,
        ),
    )
    bundle = execute_trial_plan(plan(), registry).bundles[0]
    assert bundle.status is TerminalStatus.CAPABILITY_UNAVAILABLE
    assert "P9_S3_LEGACY_P8_NOT_QUALIFIABLE" in bundle.reason_codes


def test_fixed_p8_replay_does_not_need_external_runners():
    handoff = valid_trade_handoff()
    ledger = execute_trial_plan(
        plan(mode=ExecutionMode.FIXED_P8_REPLAY, fixed=handoff),
        PhaseRunnerRegistry(),
    )
    bundle = ledger.bundles[0]
    assert bundle.status is TerminalStatus.SUCCESS
    assert len(bundle.phase_results) == 1
    assert bundle.phase_results[0].p8_handoff == handoff


def test_output_artifact_budget_fails_closed():
    registry, _ = full_registry(valid_trade_handoff())
    bundle = execute_trial_plan(plan(max_artifacts=2), registry).bundles[0]
    assert bundle.status is TerminalStatus.RESOURCE_EXHAUSTED
    assert "P9_S3_TRIAL_RESOURCE_EXHAUSTED" in bundle.reason_codes
