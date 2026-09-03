from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s10_memory_release.models import (
    P3ResearchContextHandoff,
    ResearchMemorySnapshot,
)

from tests.s10.conftest import NOW, valid_s10_input


def test_naive_datetime_is_rejected() -> None:
    inputs = valid_s10_input()
    payload = inputs.model_dump(mode="python")
    payload["created_at"] = datetime(2026, 8, 3, 18, 0)
    with pytest.raises(ValidationError):
        type(inputs).model_validate(payload)


def test_extra_field_is_rejected() -> None:
    inputs = valid_s10_input()
    payload = inputs.model_dump(mode="python")
    payload["unexpected"] = "forbidden"
    with pytest.raises(ValidationError):
        type(inputs).model_validate(payload)


def test_research_memory_hash_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ResearchMemorySnapshot(
            memory_id="memory",
            generation=0,
            items=(),
            snapshot_sha256="0" * 64,
        )


def test_p3_handoff_cannot_write_world_memory() -> None:
    with pytest.raises(ValidationError):
        P3ResearchContextHandoff(
            state="NO_EXPORTABLE_CONTEXT",
            context_items=(),
            world_memory_write_allowed=True,
        )


def test_delivery_hash_mismatch_is_rejected() -> None:
    output = __import__(
        "quant_pipeline.phase_09.subphases.s10_memory_release",
        fromlist=["run_s10_subphase"],
    ).run_s10_subphase(inputs=valid_s10_input())
    payload = output.model_dump(mode="python")
    payload["delivery_sha256"] = "0" * 64
    with pytest.raises(ValidationError):
        type(output).model_validate(payload)
