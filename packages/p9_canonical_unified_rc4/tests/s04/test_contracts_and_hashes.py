from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    QualificationState,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.common import content_sha256
from quant_pipeline.phase_09.subphases.s04_performance_risk.registries import (
    default_metric_registry,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import (
    QualifiedBacktestInput,
)


def test_qualified_input_rejects_wrong_handoff_hash(qualified):
    receipt = qualified.qualification.model_copy(
        update={"qualified_handoff_sha256": "0" * 64}
    )
    with pytest.raises(ValidationError):
        QualifiedBacktestInput(
            configuration_id=qualified.configuration_id,
            handoff=qualified.handoff,
            qualification=receipt,
        )


def test_qualified_input_rejects_invalid_state(qualified):
    body = qualified.qualification.model_dump(mode="python", exclude={"content_sha256"})
    body["state"] = QualificationState.INVALID
    body["qualified_handoff_sha256"] = None
    body["reason_codes"] = ("P9_BACKTEST_INVALID",)
    receipt = qualified.qualification.__class__(
        **body,
        content_sha256=content_sha256(body),
    )
    with pytest.raises(ValidationError):
        QualifiedBacktestInput(
            configuration_id=qualified.configuration_id,
            handoff=qualified.handoff,
            qualification=receipt,
        )


def test_metric_registry_rejects_tampered_hash():
    registry = default_metric_registry()
    with pytest.raises(ValidationError):
        registry.__class__(
            **registry.model_dump(mode="python", exclude={"content_sha256"}),
            content_sha256="0" * 64,
        )


def test_point_in_time_models_reject_non_utc(risk_free):
    first = risk_free.points[0]
    bad = first.model_copy(
        update={"timestamp": first.timestamp.astimezone(first.timestamp.tzinfo) + timedelta(0)}
    )
    # model_copy is intentionally not a validation boundary; reconstructing is.
    payload = bad.model_dump(mode="python")
    payload["timestamp"] = first.timestamp.astimezone(
        __import__("datetime").timezone(timedelta(hours=3))
    )
    with pytest.raises(ValidationError):
        first.__class__(**payload)


def test_registry_pattern_prefers_specific_entry():
    registry = default_metric_registry()
    entry = registry.get("factor.CAPM.alpha_annualized", "1.0.0")
    assert entry.metric_pattern == "factor.*.alpha_annualized"
