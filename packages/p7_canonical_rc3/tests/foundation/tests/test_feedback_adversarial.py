from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M04_promoted_ranking_feedback_loader import run_module
from tests.foundation.tests.test_m04_feedback import feedback_pair


def test_rejects_unpromoted_feedback_manifest(module_config):
    report, manifest = feedback_pair(module_config)
    manifest["promotion_status"] = "DRAFT"
    with pytest.raises(P7S1Error) as exc_info:
        run_module({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc_info.value.code == "P7_FEEDBACK_NOT_PROMOTED"


def test_rejects_direct_rank_feedback(module_config):
    report, manifest = feedback_pair(module_config)
    report = deepcopy(report)
    report["records"][0]["rank"] = 1
    with pytest.raises(P7S1Error) as exc_info:
        run_module({"ranking_feedback_report": report, "ranking_feedback_manifest": manifest}, module_config)
    assert exc_info.value.code == "P7_FEEDBACK_SCOPE_MISMATCH"
