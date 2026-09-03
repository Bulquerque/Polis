from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import (
    ArtifactReference,
    Availability,
    TerminalStatus,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.execution_models import (
    PhaseName,
    PhaseRunRequest,
    PhaseRunResult,
    RunnerCapability,
    finalize_phase_run_result,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    CandidateTerminalRecord,
    CandidateTerminalState,
    CashCategory,
    CashLedgerEntry,
    FillRecord,
    OrderRecord,
    OrderStatus,
    P8EvaluationHandoff,
    PositionSnapshot,
    Side,
    ValuationRecord,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m04_integrity_replay import (
    finalize_handoff_replay_hash,
)


BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)
ZERO_HASH = "0" * 64


def utc_day(day: int) -> datetime:
    return BASE_TIME + timedelta(days=day)


def artifact(
    *,
    artifact_id: str,
    producer: str = "P8.S5.M03",
    run_id: str = "run-1",
    cycle_id: str = "cycle-1",
    available_at: datetime | None = None,
) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=artifact_id,
        artifact_type="TEST_ARTIFACT",
        artifact_schema_name="TestArtifact",
        artifact_schema_version="1.0.0",
        content_sha256=content_sha256({"artifact_id": artifact_id}),
        producer_module_id=producer,
        run_id=run_id,
        cycle_id=cycle_id,
        available_at=available_at or utc_day(1),
        location=f"memory://{artifact_id}",
        availability=Availability.AVAILABLE,
        record_count=1,
    )


def valid_trade_handoff(
    *,
    trial_id: str = "trial-1",
    fold_id: str = "outer_000",
    capability: str = "PRODUCTION",
) -> P8EvaluationHandoff:
    order = OrderRecord(
        order_id="order-1",
        candidate_id="candidate-1",
        instrument_id="ABC",
        side=Side.BUY,
        quantity=Decimal("2"),
        decision_time=utc_day(10),
        available_at=utc_day(10),
        status=OrderStatus.FILLED,
    )
    fill = FillRecord(
        fill_id="fill-1",
        order_id="order-1",
        instrument_id="ABC",
        side=Side.BUY,
        quantity=Decimal("2"),
        price=Decimal("10"),
        fee=Decimal("1"),
        fill_time=utc_day(10),
        available_at=utc_day(10),
    )
    cash_entry = CashLedgerEntry(
        entry_id="cash-1",
        event_time=utc_day(10),
        amount=Decimal("-21"),
        category=CashCategory.FILL,
        related_fill_id="fill-1",
    )
    handoff = P8EvaluationHandoff(
        handoff_id=f"handoff:{trial_id}:{fold_id}",
        schema_version="1.0.0",
        run_id="run-1",
        cycle_id="cycle-1",
        trial_id=trial_id,
        fold_id=fold_id,
        capability=capability,
        start_cash=Decimal("100"),
        end_cash=Decimal("79"),
        p6_candidate_ids=("candidate-1",),
        p7_terminal_records=(
            CandidateTerminalRecord(candidate_id="candidate-1", state=CandidateTerminalState.RANKED),
        ),
        p8_terminal_records=(
            CandidateTerminalRecord(candidate_id="candidate-1", state=CandidateTerminalState.EXECUTED),
        ),
        orders=(order,),
        fills=(fill,),
        cash_entries=(cash_entry,),
        lifecycle_events=(),
        final_positions=(
            PositionSnapshot(
                instrument_id="ABC",
                quantity=Decimal("2"),
                market_value=Decimal("22"),
            ),
        ),
        valuations=(
            ValuationRecord(
                valuation_time=utc_day(11),
                cash=Decimal("79"),
                market_value=Decimal("22"),
                gross_pnl=Decimal("2"),
                costs=Decimal("1"),
                net_pnl=Decimal("1"),
                nav=Decimal("101"),
            ),
        ),
        required_lifecycle_supported=True,
        replay_sha256=ZERO_HASH,
    )
    return finalize_handoff_replay_hash(handoff)


def no_action_handoff(*, trial_id: str = "trial-na", fold_id: str = "outer_000") -> P8EvaluationHandoff:
    handoff = P8EvaluationHandoff(
        handoff_id=f"handoff:{trial_id}:{fold_id}",
        schema_version="1.0.0",
        run_id="run-1",
        cycle_id="cycle-1",
        trial_id=trial_id,
        fold_id=fold_id,
        capability="PRODUCTION",
        start_cash=Decimal("100"),
        end_cash=Decimal("100"),
        p6_candidate_ids=("candidate-1",),
        p7_terminal_records=(
            CandidateTerminalRecord(candidate_id="candidate-1", state=CandidateTerminalState.ABSTAINED),
        ),
        p8_terminal_records=(
            CandidateTerminalRecord(candidate_id="candidate-1", state=CandidateTerminalState.NO_ACTION),
        ),
        orders=(),
        fills=(),
        cash_entries=(),
        lifecycle_events=(),
        final_positions=(),
        valuations=(
            ValuationRecord(
                valuation_time=utc_day(11),
                cash=Decimal("100"),
                market_value=Decimal("0"),
                gross_pnl=Decimal("0"),
                costs=Decimal("0"),
                net_pnl=Decimal("0"),
                nav=Decimal("100"),
            ),
        ),
        required_lifecycle_supported=True,
        replay_sha256=ZERO_HASH,
    )
    return finalize_handoff_replay_hash(handoff)


class FakePhaseRunner:
    def __init__(
        self,
        phase: PhaseName,
        *,
        status: TerminalStatus = TerminalStatus.SUCCESS,
        p8_handoff: P8EvaluationHandoff | None = None,
        capability: RunnerCapability = RunnerCapability.PRODUCTION,
    ) -> None:
        self.phase = phase
        self.status = status
        self.p8_handoff = p8_handoff
        self._capability = capability
        self.requests: list[PhaseRunRequest] = []

    @property
    def runner_id(self) -> str:
        return f"fake:{self.phase.value}"

    @property
    def capability(self) -> RunnerCapability:
        return self._capability

    def run(self, request: PhaseRunRequest) -> PhaseRunResult:
        self.requests.append(request)
        started = utc_day(20)
        completed = utc_day(20) + timedelta(seconds=1)
        output = artifact(
            artifact_id=f"{request.trial_id}:{self.phase.value}",
            producer=f"EXTERNAL.{self.phase.value}.FAKE",
            run_id=request.run_id,
            cycle_id=request.cycle_id,
            available_at=completed,
        )
        body = {
            "phase": self.phase,
            "runner_id": self.runner_id,
            "runner_version": "1.0.0",
            "capability": self.capability,
            "status": self.status,
            "started_at": started,
            "completed_at": completed,
            "input_artifacts": request.input_artifacts,
            "output_artifacts": (output,),
            "reason_codes": () if self.status in {TerminalStatus.SUCCESS, TerminalStatus.NO_ACTION_VALID} else ("FAKE_FAILURE",),
            "p8_handoff": self.p8_handoff if self.phase is PhaseName.P8 else None,
        }
        return finalize_phase_run_result(PhaseRunResult(**body, result_sha256="0" * 64))


@pytest.fixture
def valid_handoff() -> P8EvaluationHandoff:
    return valid_trade_handoff()
