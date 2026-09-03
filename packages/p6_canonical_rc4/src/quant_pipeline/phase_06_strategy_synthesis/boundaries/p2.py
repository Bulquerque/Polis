"""P2 market input parsing and point-in-time validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from ..domain.models import ExecutableQuote, OptionContractReference, UnderlyingObservation
from ..foundation.contracts import parse_external_records
from ..foundation.errors import Phase6ContractError

T = TypeVar("T", bound=BaseModel)


def _ensure_available(records: tuple[T, ...], decision_time: datetime, module_id: str) -> None:
    for record in records:
        available_at = getattr(record, "available_at", None)
        if available_at is not None and available_at > decision_time:
            raise Phase6ContractError(
                "future market record detected",
                "P6_MARKET_CLOCK_MISMATCH",
                module_id,
                {"record": record.model_dump(mode="json")},
            )


def parse_contracts(inputs: dict[str, Any], module_id: str) -> tuple[OptionContractReference, ...]:
    return parse_external_records(
        inputs.get("clean_option_contract_panel"),
        OptionContractReference,
        "clean_option_contract_panel",
        module_id,
    )


def parse_quotes(
    inputs: dict[str, Any],
    decision_time: datetime,
    module_id: str,
) -> tuple[ExecutableQuote, ...]:
    records = parse_external_records(
        inputs.get("clean_option_quotes_panel"),
        ExecutableQuote,
        "clean_option_quotes_panel",
        module_id,
    )
    _ensure_available(records, decision_time, module_id)
    return records


def parse_underlyings(
    inputs: dict[str, Any],
    decision_time: datetime,
    module_id: str,
) -> tuple[UnderlyingObservation, ...]:
    records = parse_external_records(
        inputs.get("clean_underlying_trade_panel"),
        UnderlyingObservation,
        "clean_underlying_trade_panel",
        module_id,
    )
    _ensure_available(records, decision_time, module_id)
    return records
