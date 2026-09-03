from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.application.reconciliation import load_scoring_bundle
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.config import S7Config
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.abstention import candidate_abstention_reasons
from quant_pipeline.phase_07_strategy_tournament.finalization.subphases.s7_safety_diversity.safety import evaluate_safety


def _candidate_map(input_payload, s7_config):
    cfg = S7Config.model_validate(s7_config)
    bundle = load_scoring_bundle(input_payload, "TEST", cfg.forbidden_fields)
    return {candidate.candidate_id: candidate for candidate in bundle.candidates}, bundle, cfg


@pytest.mark.unit
def test_invalid_defined_risk_is_blocked(input_payload, s7_config):
    candidates, bundle, cfg = _candidate_map(input_payload, s7_config)
    upstream = bundle.preblocks["D"].reason_codes
    outcome = evaluate_safety(candidates["D"], 0.5, cfg.safety, upstream)
    assert outcome.blocked
    assert "P7_UPSTREAM_DEFINED_RISK_INVALID" in outcome.reason_codes
    assert "P7_UPSTREAM_ELIGIBILITY_BLOCK" in outcome.reason_codes


@pytest.mark.unit
def test_moderate_ood_abstains_but_does_not_hard_block(input_payload, s7_config):
    candidates, _, cfg = _candidate_map(input_payload, s7_config)
    safety = evaluate_safety(candidates["C"], 0.5, cfg.safety, ())
    abstention = candidate_abstention_reasons(candidates["C"], cfg.abstention)
    assert not safety.blocked
    assert "P7_MODERATE_OOD_ABSTAIN" in abstention


@pytest.mark.unit
def test_low_confidence_abstains(input_payload, s7_config):
    candidates, _, cfg = _candidate_map(input_payload, s7_config)
    reasons = candidate_abstention_reasons(candidates["F"], cfg.abstention)
    assert "P7_CONFIDENCE_BELOW_MINIMUM" in reasons


@pytest.mark.unit
def test_stale_execution_context_is_blocked(input_payload, s7_config):
    from dataclasses import replace

    candidates, _, cfg = _candidate_map(input_payload, s7_config)
    stale = replace(candidates["A"], execution_context_time=candidates["A"].decision_time - timedelta(days=2))
    outcome = evaluate_safety(stale, 0.5, cfg.safety, ())
    assert outcome.blocked
    assert "P7_STALE_EXECUTION_CONTEXT" in outcome.reason_codes


@pytest.mark.unit
def test_severe_ood_is_hard_block(input_payload, s7_config):
    from dataclasses import replace

    candidates, _, cfg = _candidate_map(input_payload, s7_config)
    severe = replace(candidates["A"], ood_severity="SEVERE")
    outcome = evaluate_safety(severe, 0.5, cfg.safety, ())
    assert outcome.blocked
    assert "P7_SEVERE_OOD_BLOCK_POLICY" in outcome.reason_codes
