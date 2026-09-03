"""P9.S7.M01 — append-only prequential prediction/decision/outcome stream."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import Field, StringConstraints, field_validator, model_validator

from .canonical import payload_sha256
from .contracts import EvidenceClass, MaturityState, NonEmptyStr, StrictModel
from .errors import ContractError, TemporalIntegrityError

FiniteProbability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class ForecastKind(StrEnum):
    POINT = "POINT"
    BINARY_PROBABILITY = "BINARY_PROBABILITY"
    NORMAL = "NORMAL"
    QUANTILES = "QUANTILES"
    INTERVAL = "INTERVAL"


class DecisionKind(StrEnum):
    ACTION = "ACTION"
    NO_ACTION = "NO_ACTION"
    ABSTAIN = "ABSTAIN"


class PointForecast(StrictModel):
    kind: Literal[ForecastKind.POINT] = ForecastKind.POINT
    value: float


class BinaryProbabilityForecast(StrictModel):
    kind: Literal[ForecastKind.BINARY_PROBABILITY] = ForecastKind.BINARY_PROBABILITY
    probability: FiniteProbability


class NormalForecast(StrictModel):
    kind: Literal[ForecastKind.NORMAL] = ForecastKind.NORMAL
    mean: float
    standard_deviation: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


class QuantilePoint(StrictModel):
    quantile: Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)]
    value: float


class QuantileForecast(StrictModel):
    kind: Literal[ForecastKind.QUANTILES] = ForecastKind.QUANTILES
    points: tuple[QuantilePoint, ...]

    @model_validator(mode="after")
    def validate_quantiles(self) -> "QuantileForecast":
        if len(self.points) < 2:
            raise ValueError("quantile forecast requires at least two points")
        quantiles = [point.quantile for point in self.points]
        values = [point.value for point in self.points]
        if quantiles != sorted(quantiles) or len(set(quantiles)) != len(quantiles):
            raise ValueError("quantiles must be unique and strictly increasing")
        if any(left > right for left, right in zip(values, values[1:], strict=False)):
            raise ValueError("quantile values must be nondecreasing")
        return self


class IntervalForecast(StrictModel):
    kind: Literal[ForecastKind.INTERVAL] = ForecastKind.INTERVAL
    lower: float
    upper: float
    nominal_coverage: Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_interval(self) -> "IntervalForecast":
        if self.lower > self.upper:
            raise ValueError("interval lower must not exceed upper")
        return self


ForecastPayload = Annotated[
    Union[
        PointForecast,
        BinaryProbabilityForecast,
        NormalForecast,
        QuantileForecast,
        IntervalForecast,
    ],
    Field(discriminator="kind"),
]


class PredictionEvent(StrictModel):
    event_id: NonEmptyStr
    cohort_id: NonEmptyStr
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    target_id: NonEmptyStr
    horizon_id: NonEmptyStr
    issued_at: datetime
    information_set_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    forecast: ForecastPayload
    decision_kind: DecisionKind
    action_id: NonEmptyStr | None = None
    regime_id: NonEmptyStr | None = None
    ood_bucket: NonEmptyStr | None = None
    confidence_bucket: NonEmptyStr | None = None

    @field_validator("issued_at")
    @classmethod
    def issued_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("issued_at must be UTC")
        return value

    @model_validator(mode="after")
    def validate_decision(self) -> "PredictionEvent":
        if self.decision_kind is DecisionKind.ACTION and self.action_id is None:
            raise ValueError("ACTION decision requires action_id")
        if self.decision_kind is not DecisionKind.ACTION and self.action_id is not None:
            raise ValueError("only ACTION decisions may carry action_id")
        return self


class OutcomeEvent(StrictModel):
    outcome_id: NonEmptyStr
    prediction_event_id: NonEmptyStr
    observed_at: datetime
    available_at: datetime
    maturity_state: MaturityState
    evidence_class: EvidenceClass
    value: float | None
    vintage_id: NonEmptyStr
    supersedes_outcome_id: NonEmptyStr | None = None

    @field_validator("observed_at", "available_at")
    @classmethod
    def outcome_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("outcome clocks must be UTC")
        return value

    @model_validator(mode="after")
    def validate_outcome(self) -> "OutcomeEvent":
        if self.available_at < self.observed_at:
            raise ValueError("available_at must not precede observed_at")
        has_value = self.value is not None
        evaluable = self.maturity_state in {MaturityState.MATURED, MaturityState.SETTLED}
        if evaluable and not has_value:
            raise ValueError("matured or settled outcome requires value")
        if not evaluable and has_value and self.evidence_class is EvidenceClass.FACTUAL_EXECUTED:
            raise ValueError("non-mature factual executed outcome cannot carry final value")
        return self


class PrequentialRecord(StrictModel):
    prediction: PredictionEvent
    outcomes: tuple[OutcomeEvent, ...] = ()
    active_outcome_id: NonEmptyStr | None = None
    record_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def validate_record(self) -> "PrequentialRecord":
        for outcome in self.outcomes:
            if outcome.prediction_event_id != self.prediction.event_id:
                raise ValueError("outcome references a different prediction event")
            if outcome.available_at <= self.prediction.issued_at:
                raise ValueError("outcome must become available after prediction issuance")
        ids = [outcome.outcome_id for outcome in self.outcomes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate outcome_id in record")
        if self.active_outcome_id is not None and self.active_outcome_id not in ids:
            raise ValueError("active_outcome_id must reference an outcome in the record")
        return self

    @property
    def active_outcome(self) -> OutcomeEvent | None:
        if self.active_outcome_id is None:
            return None
        return next(
            outcome
            for outcome in self.outcomes
            if outcome.outcome_id == self.active_outcome_id
        )


class MaturityQueueItem(StrictModel):
    prediction_event_id: NonEmptyStr
    issued_at: datetime
    maturity_state: MaturityState
    latest_outcome_available_at: datetime | None = None


class StreamIntegrityReceipt(StrictModel):
    record_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    matured_count: int = Field(ge=0)
    no_action_count: int = Field(ge=0)
    stream_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    reason_codes: tuple[NonEmptyStr, ...] = ()


class PrequentialStreamResult(StrictModel):
    records: tuple[PrequentialRecord, ...]
    maturity_queue: tuple[MaturityQueueItem, ...]
    receipt: StreamIntegrityReceipt


def _record_hash(
    prediction: PredictionEvent,
    outcomes: tuple[OutcomeEvent, ...],
    active_id: str | None,
) -> str:
    payload = {
        "prediction": prediction.model_dump(mode="json"),
        "outcomes": [outcome.model_dump(mode="json") for outcome in outcomes],
        "active_outcome_id": active_id,
    }
    return payload_sha256(payload)


def _choose_active_outcome(outcomes: tuple[OutcomeEvent, ...]) -> str | None:
    if not outcomes:
        return None
    superseded = {
        outcome.supersedes_outcome_id
        for outcome in outcomes
        if outcome.supersedes_outcome_id
    }
    candidates = [outcome for outcome in outcomes if outcome.outcome_id not in superseded]
    if len(candidates) != 1:
        raise ContractError("outcome revision chain must have exactly one active leaf")
    return candidates[0].outcome_id


def build_prequential_stream(
    predictions: tuple[PredictionEvent, ...],
    outcomes: tuple[OutcomeEvent, ...],
    existing_records: tuple[PrequentialRecord, ...] = (),
) -> PrequentialStreamResult:
    """Build or replay an append-only prequential stream.

    Duplicate identical events are idempotent. A duplicate ID with different
    content is a hard integrity failure.
    """

    prediction_by_id: dict[str, PredictionEvent] = {
        record.prediction.event_id: record.prediction for record in existing_records
    }
    outcome_by_id: dict[str, OutcomeEvent] = {
        outcome.outcome_id: outcome
        for record in existing_records
        for outcome in record.outcomes
    }

    for prediction in predictions:
        previous = prediction_by_id.get(prediction.event_id)
        if previous is not None and previous != prediction:
            raise ContractError("P9_LIVE_PREQUENTIAL_DUPLICATE_CONFLICT")
        prediction_by_id[prediction.event_id] = prediction

    for outcome in outcomes:
        if outcome.prediction_event_id not in prediction_by_id:
            raise ContractError("P9_LINEAGE_REFERENCE_UNRESOLVED")
        prediction = prediction_by_id[outcome.prediction_event_id]
        if outcome.available_at <= prediction.issued_at:
            raise TemporalIntegrityError("P9_TEMPORAL_INFORMATION_SET_AFTER_DECISION")
        previous = outcome_by_id.get(outcome.outcome_id)
        if previous is not None and previous != outcome:
            raise ContractError("P9_LIVE_PREQUENTIAL_DUPLICATE_CONFLICT")
        outcome_by_id[outcome.outcome_id] = outcome

    records: list[PrequentialRecord] = []
    queue: list[MaturityQueueItem] = []
    ordered_predictions = sorted(
        prediction_by_id.values(),
        key=lambda item: (item.issued_at, item.event_id),
    )
    for prediction in ordered_predictions:
        linked = tuple(
            sorted(
                (
                    outcome
                    for outcome in outcome_by_id.values()
                    if outcome.prediction_event_id == prediction.event_id
                ),
                key=lambda item: (item.available_at, item.outcome_id),
            )
        )
        active_id = _choose_active_outcome(linked)
        record = PrequentialRecord(
            prediction=prediction,
            outcomes=linked,
            active_outcome_id=active_id,
            record_sha256=_record_hash(prediction, linked, active_id),
        )
        records.append(record)
        active = record.active_outcome
        queue.append(
            MaturityQueueItem(
                prediction_event_id=prediction.event_id,
                issued_at=prediction.issued_at,
                maturity_state=active.maturity_state if active else MaturityState.NOT_MATURED,
                latest_outcome_available_at=active.available_at if active else None,
            )
        )

    matured = sum(
        item.maturity_state in {MaturityState.MATURED, MaturityState.SETTLED} for item in queue
    )
    pending = len(queue) - matured
    no_action = sum(record.prediction.decision_kind is DecisionKind.NO_ACTION for record in records)
    stream_hash = payload_sha256([record.model_dump(mode="json") for record in records])
    receipt = StreamIntegrityReceipt(
        record_count=len(records),
        pending_count=pending,
        matured_count=matured,
        no_action_count=no_action,
        stream_sha256=stream_hash,
    )
    return PrequentialStreamResult(
        records=tuple(records),
        maturity_queue=tuple(queue),
        receipt=receipt,
    )
