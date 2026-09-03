from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import InstrumentSpec

from .errors import PositionIntegrityError
from .input_models import S8InputBundle


def instrument_registry(value: S8InputBundle) -> dict[str, InstrumentSpec]:
    result: dict[str, InstrumentSpec] = {}
    for item in (*value.s7_handoff.authorization_bundle.instruments, *value.supplemental_instruments):
        prior = result.get(item.instrument_id)
        if prior is not None and prior != item:
            raise PositionIntegrityError(f"conflicting instrument spec: {item.instrument_id}")
        result[item.instrument_id] = item
    return result
