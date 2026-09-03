from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters.legacy_rc41 import (
    assess_legacy_rc41_bundle,
)


def test_legacy_adapter_never_fabricates_new_contract() -> None:
    report = assess_legacy_rc41_bundle(
        {
            "ranked_candidate_panel": [
                {
                    "candidate_id": "cand-1",
                    "score_confidence": 1.0,
                    "liquidity_score": 1.0,
                }
            ]
        }
    )
    assert report.mode == "LOSSY_UNSUPPORTED"
    assert "p6_economic_package_ref" in report.missing_semantics
    assert report.forbidden_defaults_detected == ("liquidity_score", "score_confidence")
