from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_05_underlying_forecasts.domain.core import ArtifactReference
from quant_pipeline.phase_05_underlying_forecasts.domain.distributions import QuantileDistribution, QuantilePoint
from quant_pipeline.phase_05_underlying_forecasts.domain.forecast import ForecastMemberRecord
from quant_pipeline.phase_05_underlying_forecasts.errors import ArtifactError
from quant_pipeline.phase_05_underlying_forecasts.stores import JsonArtifactStore


def test_artifact_reference_rejects_path_escape():
    with pytest.raises(ValidationError):
        ArtifactReference(
            artifact_id="x",
            artifact_type="x",
            storage_uri="../escape.json",
            content_hash="a" * 64,
        )


def test_store_is_content_addressed_and_checks_finite(tmp_path):
    store = JsonArtifactStore(tmp_path)
    first = store.write("example", {"records": [{"value": 1.0}]})
    second = store.write("example", {"records": [{"value": 1.0}]})
    assert first == second
    assert store.read(first)["records"][0]["value"] == 1.0
    with pytest.raises(ValueError):
        store.write("bad", {"value": float("nan")})


def test_store_read_rejects_path_escape(tmp_path):
    store = JsonArtifactStore(tmp_path)
    reference = ArtifactReference(
        artifact_id="x",
        artifact_type="x",
        storage_uri="safe.json",
        content_hash="a" * 64,
    )
    object.__setattr__(reference, "storage_uri", "../escape.json")
    with pytest.raises(ArtifactError):
        store.read(reference)


def test_forecast_member_enforces_pit_and_monotonic_quantiles():
    now = datetime(2025, 1, 2, tzinfo=timezone.utc)
    distribution = QuantileDistribution(quantiles=(
        QuantilePoint(level=0.05, value=-1.0),
        QuantilePoint(level=0.50, value=0.0),
        QuantilePoint(level=0.95, value=1.0),
    ))
    record = ForecastMemberRecord(
        record_id="r",
        as_of_time=now,
        prediction_timestamp=now + timedelta(days=1),
        underlying="AAA",
        target_id="return",
        horizon="1D",
        unit="decimal_return",
        resolver_id="ridge",
        resolver_family="LINEAR",
        model_artifact_id="m",
        feature_view_id="TABULAR_INTERPRETABLE",
        training_cutoff=now - timedelta(days=1),
        lineage_id="l",
        distribution=distribution,
    )
    assert record.point_forecast == 0.0


def test_quantiles_reject_non_monotonic_values():
    with pytest.raises(ValidationError):
        QuantileDistribution(quantiles=(
            QuantilePoint(level=0.05, value=1.0),
            QuantilePoint(level=0.95, value=-1.0),
        ))


def test_forecast_member_rejects_future_training_cutoff():
    now = datetime(2025, 1, 2, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        ForecastMemberRecord(
            record_id="r",
            as_of_time=now,
            prediction_timestamp=now + timedelta(days=1),
            underlying="AAA",
            target_id="return",
            horizon="1D",
            unit="decimal_return",
            resolver_id="ridge",
            resolver_family="LINEAR",
            model_artifact_id="m",
            feature_view_id="TABULAR_INTERPRETABLE",
            training_cutoff=now + timedelta(days=1),
            lineage_id="l",
            distribution=QuantileDistribution(quantiles=(
                QuantilePoint(level=0.05, value=-1.0),
                QuantilePoint(level=0.95, value=1.0),
            )),
        )
