from __future__ import annotations

import numpy as np

from quant_pipeline.phase_04_feature_base.s8.decoder import decode_encoder, decode_linear, observed_rmse


def test_linear_decoder_reconstructs_saved_pca_state() -> None:
    state = {"components": [[1.0, 0.0], [0.0, 1.0]], "mean": [10.0, -2.0]}
    scores = [[0.5, -1.5], [2.0, 3.0]]
    decoded = decode_linear(scores, state)
    expected = np.asarray(scores) + np.asarray(state["mean"])
    assert np.allclose(decoded, expected)
    assert observed_rmse(decoded, expected) == 0.0


def test_encoder_decoder_uses_portable_saved_weights() -> None:
    state = {
        "model_state": {
            "weights": {
                "decoder.weight": [[1.0, 2.0, 3.0]],
                "decoder.bias": [0.5],
            }
        }
    }
    decoded = decode_encoder([[1.0, 2.0]], {"private": [3.0]}, state)
    assert np.allclose(decoded, [[14.5]])
