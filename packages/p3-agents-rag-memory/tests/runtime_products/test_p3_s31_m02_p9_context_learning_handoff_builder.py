from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S31_M02_p9_context_learning_handoff_builder import (
    IMPLEMENTED,
    MODULE_ID,
    MODULE_NAME,
    REQUIRED_INPUTS,
    run_module,
)
from quant_pipeline.phase_03_agents_rag_memory.s31_products import S31AuthorityError, S31IntegrityError
from .s31_support import compatibility_config, execution_context, m01_inputs, run_m01, run_m02


def test_module_identity_and_status():
    assert MODULE_ID == "P3.S31.M02"
    assert MODULE_NAME == "p9_context_learning_handoff_builder"
    assert IMPLEMENTED is True
    assert len(REQUIRED_INPUTS) == 4


def test_builds_current_unbound_handoff():
    manifest = run_m02()
    assert manifest["complete"] is True
    assert manifest["consumer_binding_status"] == "CONSUMER_NOT_YET_BOUND"
    assert manifest["quality_status"] == "DEGRADED"
    assert "P9_CONSUMER_NOT_YET_BOUND" in manifest["quality_reasons"]
    assert manifest["contains_evaluation_results"] is False
    assert manifest["contains_promotion_decision"] is False
    assert set(manifest["artifact_hashes"]) == set(REQUIRED_INPUTS)


def test_detects_phase4_tampering_after_bundle_creation():
    inputs = m01_inputs()
    bundle = run_m01(inputs)
    inputs["phase4_social_handoff_manifest"]["quality_reasons"] = ["tampered"]
    with pytest.raises(S31IntegrityError, match="phase4_social_handoff_manifest"):
        run_m02(bundle=bundle, inputs=inputs)


def test_rejects_evaluation_results_in_bundle():
    bundle = run_m01()
    bundle["contains_evaluation_results"] = True
    with pytest.raises(Exception, match="contains_evaluation_results"):
        run_m02(bundle=bundle)


def test_wrapper_requires_consumer_compatibility_config():
    with pytest.raises(ValueError, match="p9_consumer_compatibility"):
        run_module({}, {"execution_context": execution_context()})


def test_config_cannot_claim_bound_consumer_before_p9_contract_adopts_inputs():
    config = compatibility_config()
    config["consumer_binding_status"] = "READY_FOR_BOUND_P9"
    with pytest.raises(Exception, match="cannot be READY_FOR_BOUND_P9"):
        run_m02(compatibility=config)


def test_forbidden_promotion_field_is_rejected_recursively():
    bundle = run_m01()
    bundle["promotion_decision"] = "PROMOTE"
    with pytest.raises(S31AuthorityError, match="promotion_decision"):
        run_m02(bundle=bundle)
