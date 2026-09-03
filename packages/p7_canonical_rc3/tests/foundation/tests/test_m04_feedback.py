from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.artifacts import create_artifact
from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
from quant_pipeline.phase_07_strategy_tournament.foundation.models import ModuleConfig
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M04_promoted_ranking_feedback_loader import run_module


def feedback_pair(module_config):
    config = ModuleConfig.model_validate(module_config)
    report = create_artifact(
        artifact_name="ranking_feedback_report",
        records=[{
            "feedback_id": "fb-1",
            "source_cycle_id": "cycle-1",
            "source_cycle_sequence": 1,
            "target_cycle_id": "cycle-2",
            "target_cycle_sequence": 2,
            "promotion_status": "PROMOTED",
            "scope": {"phase": "P7"},
            "evidence_ids": ["evidence-1"],
            "valid_from_cycle_sequence": 2,
            "expires_at": "2026-02-01T00:00:00Z",
            "adjustments": [{
                "adjustment_type": "POLICY_PARAMETER_BOUND",
                "parameter": "max_cost_ratio",
                "value": 0.2,
            }],
        }],
        producer_module_id="P9.S6.M01",
        context=config.context,
        grain="one_record_per_feedback_item",
    ).model_copy(update={"producer_phase": "P9", "destination_phase": "P7"})
    # Recompute after producer update.
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256
    dumped = report.model_dump(mode="json", exclude={"content_sha256"})
    report = report.model_copy(update={"content_sha256": content_sha256(dumped)})
    manifest = {
        "manifest_id": "p9-feedback-manifest-1",
        "schema_version": "2.0.0",
        "producer_phase": "P9",
        "destination_phase": "P7",
        "source_cycle_id": "cycle-1",
        "source_cycle_sequence": 1,
        "target_cycle_id": "cycle-2",
        "target_cycle_sequence": 2,
        "promotion_status": "PROMOTED",
        "report_artifact_id": report.artifact_id,
        "report_content_sha256": report.content_sha256,
        "decision_time": "2026-01-05T14:30:00Z",
        "created_at": "2026-01-05T14:31:00Z",
    }
    return report.model_dump(mode="json"), manifest


def test_absent_feedback_is_explicitly_valid(module_config):
    result = run_module({"ranking_feedback_report": None, "ranking_feedback_manifest": None}, module_config)
    context = result["outputs"]["ranking_feedback_context"]
    assert context["record_count"] == 0
    assert context["capability_status"] == "UNAVAILABLE"


def test_loads_promoted_previous_cycle_feedback(module_config):
    report, manifest = feedback_pair(module_config)
    config = deepcopy(module_config)
    config["policy"] = {"allowed_scope": {"phase": "P7"}}
    result = run_module({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, config)
    assert result["outputs"]["ranking_feedback_context"]["record_count"] == 1


def test_rejects_current_cycle_feedback(module_config):
    report, manifest = feedback_pair(module_config)
    manifest["source_cycle_sequence"] = 2
    with pytest.raises(P7S1Error) as exc_info:
        run_module({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc_info.value.code == "P7_FEEDBACK_CURRENT_CYCLE"
