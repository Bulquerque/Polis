from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.contracts import RunContext


def test_extra_fields_are_rejected(context) -> None:
    payload = context.model_dump(mode="python")
    payload["unknown"] = "not allowed"
    with pytest.raises(ValidationError):
        RunContext.model_validate(payload)


def test_naive_datetimes_are_rejected(context) -> None:
    payload = context.model_dump(mode="python")
    payload["decision_time"] = datetime(2025, 1, 1)
    with pytest.raises(ValidationError):
        RunContext.model_validate(payload)
