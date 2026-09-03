from __future__ import annotations

from quant_pipeline.phase_04_feature_base.runtime.module_api import context_from_config


def test_legacy_phase_config_is_promoted_to_deterministic_context() -> None:
    context = context_from_config(
        {
            "pipeline_version": "V14.1-RC4.1",
            "created_at": "2024-06-01T00:00:00Z",
            "as_of_date": "2024-06-01T23:59:59Z",
        }
    )
    assert context.run_id == "legacy-module-run"
    assert context.cycle_id == "legacy-module-cycle"
    assert context.as_of_time.isoformat() == "2024-06-01T23:59:59+00:00"
