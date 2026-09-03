from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import (
    TerminalStatus,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.execution_models import (
    PhaseName,
    PhaseRunRequest,
    PhaseRunResult,
    ResourceBudget,
    RunnerCapability,
    TrialExecutionPlan,
    TrialSpec,
    finalize_phase_run_result,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m03_backtest_runner import (
    PhaseRunnerRegistry,
    execute_trial_plan,
)

from tests.s03.conftest import artifact, utc_day, valid_trade_handoff


class MismatchedP8Runner:
    @property
    def runner_id(self) -> str:
        return "bad:p8"

    @property
    def capability(self) -> RunnerCapability:
        return RunnerCapability.PRODUCTION

    def run(self, request: PhaseRunRequest) -> PhaseRunResult:
        handoff = valid_trade_handoff(trial_id="another-trial", fold_id=request.fold_id)
        body = {
            "phase": request.phase,
            "runner_id": self.runner_id,
            "runner_version": "1.0.0",
            "capability": self.capability,
            "status": TerminalStatus.SUCCESS,
            "started_at": utc_day(10),
            "completed_at": utc_day(10) + timedelta(seconds=1),
            "input_artifacts": request.input_artifacts,
            "output_artifacts": (
                artifact(
                    artifact_id="bad-p8-output",
                    producer="EXTERNAL.P8.BAD",
                    run_id=request.run_id,
                    cycle_id=request.cycle_id,
                ),
            ),
            "p8_handoff": handoff,
        }
        return finalize_phase_run_result(PhaseRunResult(**body, result_sha256="0" * 64))


class PassRunner:
    def __init__(self, phase: PhaseName) -> None:
        self.phase = phase

    @property
    def runner_id(self) -> str:
        return f"pass:{self.phase.value}"

    @property
    def capability(self) -> RunnerCapability:
        return RunnerCapability.PRODUCTION

    def run(self, request: PhaseRunRequest) -> PhaseRunResult:
        body = {
            "phase": request.phase,
            "runner_id": self.runner_id,
            "runner_version": "1.0.0",
            "capability": self.capability,
            "status": TerminalStatus.SUCCESS,
            "started_at": utc_day(10),
            "completed_at": utc_day(10) + timedelta(seconds=1),
            "input_artifacts": request.input_artifacts,
            "output_artifacts": (
                artifact(
                    artifact_id=f"{request.phase.value}-output",
                    producer=f"EXTERNAL.{request.phase.value}.PASS",
                    run_id=request.run_id,
                    cycle_id=request.cycle_id,
                ),
            ),
        }
        return finalize_phase_run_result(PhaseRunResult(**body, result_sha256="0" * 64))


def test_p8_handoff_with_wrong_trial_is_rejected_by_consumer_contract() -> None:
    registry = PhaseRunnerRegistry()
    for phase in (PhaseName.P5, PhaseName.P6, PhaseName.P7):
        registry.register(phase, PassRunner(phase))
    registry.register(PhaseName.P8, MismatchedP8Runner())
    plan = TrialExecutionPlan(
        plan_id="plan",
        run_id="run-1",
        cycle_id="cycle-1",
        contract_pack_version="1.0.0",
        trials=(
            TrialSpec(
                trial_id="expected-trial",
                configuration_id="config",
                configuration_sha256="a" * 64,
                fold_id="outer_000",
                seed_namespace="seed",
            ),
        ),
        resource_budget=ResourceBudget(maximum_seconds=Decimal("10")),
    )
    result = execute_trial_plan(plan, registry)
    bundle = result.bundles[0]
    assert bundle.status is TerminalStatus.INVALID
    assert "P9_S3_PHASE_CONTRACT_REJECTED" in bundle.reason_codes
    assert "P8 handoff execution identity mismatch" in bundle.reason_codes


class ForgedHashRunner(PassRunner):
    def run(self, request: PhaseRunRequest) -> PhaseRunResult:
        valid = super().run(request)
        return valid.model_copy(update={"result_sha256": "0" * 64})


def test_forged_phase_result_hash_is_rejected() -> None:
    registry = PhaseRunnerRegistry()
    registry.register(PhaseName.P5, ForgedHashRunner(PhaseName.P5))
    for phase in (PhaseName.P6, PhaseName.P7):
        registry.register(phase, PassRunner(phase))
    registry.register(PhaseName.P8, MismatchedP8Runner())
    plan = TrialExecutionPlan(
        plan_id="plan-hash",
        run_id="run-1",
        cycle_id="cycle-1",
        contract_pack_version="1.0.0",
        trials=(
            TrialSpec(
                trial_id="expected-trial",
                configuration_id="config",
                configuration_sha256="a" * 64,
                fold_id="outer_000",
                seed_namespace="seed",
            ),
        ),
        resource_budget=ResourceBudget(maximum_seconds=Decimal("10")),
    )
    bundle = execute_trial_plan(plan, registry).bundles[0]
    assert bundle.status is TerminalStatus.INVALID
    assert "phase result hash mismatch" in bundle.reason_codes
