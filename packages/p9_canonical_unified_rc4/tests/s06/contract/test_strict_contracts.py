from datetime import datetime

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import RunContext

H = "0" * 64


def test_naive_datetime_is_rejected():
    with pytest.raises(ValidationError):
        RunContext(
            run_id="r",
            cycle_id="c",
            experiment_id="e",
            configuration_id="cfg",
            decision_time=datetime(2026, 1, 1),
            available_at=datetime(2025, 12, 31),
            code_sha256=H,
            data_sha256=H,
        )


def test_extra_fields_are_rejected(context):
    payload = context.model_dump()
    payload["unexpected"] = 1
    with pytest.raises(ValidationError):
        RunContext.model_validate(payload)
