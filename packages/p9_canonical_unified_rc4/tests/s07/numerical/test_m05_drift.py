from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.m05_drift import (
    DriftChannelKind,
    DriftChannelPolicy,
    DriftObservation,
    detect_multichannel_drift,
)

pytestmark = pytest.mark.numerical


def series(base_time, channel_id: str, kind: DriftChannelKind, values):
    return tuple(
        DriftObservation(
            channel_id=channel_id,
            channel_kind=kind,
            observed_at=base_time + timedelta(minutes=i),
            value=value,
        )
        for i, value in enumerate(values)
    )


def policy(channel_id: str, kind: DriftChannelKind):
    return DriftChannelPolicy(
        channel_id=channel_id,
        channel_kind=kind,
        reference_window=30,
        test_window=10,
        mean_shift_z_threshold=2.0,
        cusum_threshold=3.0,
        bocpd_alert_probability=0.2,
    )


def test_two_channels_confirm_abrupt_shift(base_time):
    observations = series(base_time, "residual", DriftChannelKind.FORECAST_RESIDUAL, [0.0] * 30 + [5.0] * 10)
    observations += series(base_time, "cost", DriftChannelKind.COST, [0.0] * 30 + [4.0] * 10)
    result = detect_multichannel_drift(
        observations,
        (policy("residual", DriftChannelKind.FORECAST_RESIDUAL), policy("cost", DriftChannelKind.COST)),
        minimum_confirming_channels=2,
    )
    assert result.agreement.confirmed
    assert len(result.agreement.alerted_channel_ids) == 2


def test_single_channel_is_not_confirmed(base_time):
    observations = series(base_time, "residual", DriftChannelKind.FORECAST_RESIDUAL, [0.0] * 30 + [5.0] * 10)
    observations += series(base_time, "cost", DriftChannelKind.COST, [0.0] * 40)
    result = detect_multichannel_drift(
        observations,
        (policy("residual", DriftChannelKind.FORECAST_RESIDUAL), policy("cost", DriftChannelKind.COST)),
        minimum_confirming_channels=2,
    )
    assert not result.agreement.confirmed
    assert "P9_LIVE_DRIFT_SINGLE_CHANNEL_UNCONFIRMED" in result.agreement.reason_codes
