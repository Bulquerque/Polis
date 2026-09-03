from datetime import UTC, datetime
import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s08_attribution.bundle import S8ExecutionRequest
from quant_pipeline.phase_09.subphases.s08_attribution.runner import S8Pipeline


def test_scope_mismatch_is_rejected(valid_request):
    bad_header=valid_request.header.model_copy(update={"run_id":"other"})
    with pytest.raises(ValidationError):
        S8ExecutionRequest(**valid_request.model_dump(exclude={"header"}), header=bad_header)


def test_factual_pnl_mismatch_marks_m08_invalid(valid_request):
    request=valid_request.model_copy(update={"factual_pnl":99.0})
    bundle=S8Pipeline().run(request)
    assert bundle.payload.hierarchical_reconciliation.quality.value == "INVALID"
    assert "P9_ATTRIBUTION_RECONCILIATION_FAILED" in bundle.payload.hierarchical_reconciliation.reason_codes


def test_missing_counterfactual_support_is_explicit(valid_request):
    rows=tuple(item.model_copy(update={"logging_propensity":None,"direct_model_chosen_reward":None,"direct_model_target_value":None}) for item in valid_request.logged_policy_observations)
    request=valid_request.model_copy(update={"logged_policy_observations":rows})
    bundle=S8Pipeline().run(request)
    assert bundle.payload.counterfactual_report.quality.value == "NOT_IDENTIFIABLE"
    assert bundle.payload.subphase_receipt.status.value == "UNAVAILABLE"
