from __future__ import annotations

import numpy as np
import pytest

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m01_dependence_and_sampling_diagnostics import diagnose_dependence
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.m02_automatic_block_length_selector import _optimal_block_length, select_block_length
from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import DependenceDiagnosticsRequest, BlockLengthSelectionRequest


def test_politis_white_reference_value_is_stable() -> None:
    rng = np.random.default_rng(9182)
    values = np.empty(500)
    noise = rng.normal(size=500)
    values[0] = noise[0]
    for index in range(1, 500):
        values[index] = 0.6 * values[index - 1] + noise[index]
    stationary, circular = _optimal_block_length(values)
    assert stationary == pytest.approx(12.6983973834, rel=1e-10)
    assert circular == pytest.approx(14.5360363424, rel=1e-10)


def test_joint_block_is_not_smaller_than_each_series(context, series_panel) -> None:
    diagnostics = diagnose_dependence(DependenceDiagnosticsRequest(context=context, series=series_panel))
    result = select_block_length(
        BlockLengthSelectionRequest(context=context, series=series_panel, diagnostics=diagnostics)
    )
    assert result.joint_stationary_block_length == max(
        item.stationary_selected for item in result.estimates
    )

