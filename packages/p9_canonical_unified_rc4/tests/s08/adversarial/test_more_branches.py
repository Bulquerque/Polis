from datetime import UTC, datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import EvidenceClass
from quant_pipeline.phase_09.subphases.s08_attribution.bundle import ProspectiveAttributionBundle, Clock, S8ExecutionRequest
from quant_pipeline.phase_09.subphases.s08_attribution.contracts import AttributionQuality, IntegrityEnvelope, integrity_for_payload
from quant_pipeline.phase_09.subphases.s08_attribution.errors import AttributionInvariantError, ContractError, NumericalDomainError, S8Error
from quant_pipeline.phase_09.subphases.s08_attribution.m01_forecast_attribution import ForecastAttributionPolicy, ForecastComponentObservation, attribute_forecast_components
from quant_pipeline.phase_09.subphases.s08_attribution.m02_payoff_attribution import CandidateOutcome, PayoffAttributionPolicy, evaluate_payoff_fidelity
from quant_pipeline.phase_09.subphases.s08_attribution.m03_ranking_attribution import RankedCandidate, RankingAttributionPolicy, RankingGroup, evaluate_ranking
from quant_pipeline.phase_09.subphases.s08_attribution.runner import S8Pipeline


def test_error_taxonomy_is_importable():
    assert issubclass(ContractError, S8Error)
    assert issubclass(AttributionInvariantError, S8Error)
    assert issubclass(NumericalDomainError, S8Error)


def test_integrity_helper_hashes_payload():
    envelope=integrity_for_payload({"a":1})
    assert len(envelope.payload_sha256)==64


def test_clock_rejects_non_utc():
    clock=Clock(lambda:datetime.now(timezone(timedelta(hours=1))))
    with pytest.raises(ValueError):
        clock()


def test_bundle_tamper_is_rejected(valid_request):
    bundle=S8Pipeline(Clock(lambda:datetime(2026,1,4,tzinfo=UTC))).run(valid_request)
    with pytest.raises(ValidationError):
        ProspectiveAttributionBundle(payload=bundle.payload, integrity=IntegrityEnvelope(payload_sha256="0"*64))


def test_s7_scope_mismatch_is_rejected(valid_request):
    s7_header=valid_request.s7_bundle.payload.header.model_copy(update={"cycle_id":"other"})
    s7_payload=valid_request.s7_bundle.payload.model_copy(update={"header":s7_header})
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import IntegrityEnvelope as S7Integrity
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.canonical import payload_sha256
    s7=valid_request.s7_bundle.model_copy(update={"payload":s7_payload,"integrity":S7Integrity(payload_sha256=payload_sha256(s7_payload))})
    with pytest.raises(ValidationError):
        S8ExecutionRequest(**valid_request.model_dump(exclude={"s7_bundle"}), s7_bundle=s7)


def test_forecast_contract_rejects_nonzero_unconsumed_weight():
    with pytest.raises(ValidationError):
        ForecastComponentObservation(observation_id="o",target_id="t",horizon_id="h",regime_id="r",component_id="c",component_kind="MODEL",consumed=False,historical_weight=1.0,ensemble_loss=1.0,oof_qualified=True,evidence_class=EvidenceClass.UNAVAILABLE)


def test_forecast_contract_requires_both_pnl_values():
    with pytest.raises(ValidationError):
        ForecastComponentObservation(observation_id="o",target_id="t",horizon_id="h",regime_id="r",component_id="c",component_kind="MODEL",consumed=True,historical_weight=1.0,ensemble_loss=1.0,ablated_loss=2.0,oof_qualified=True,observable_pnl_with_component=1.0,evidence_class=EvidenceClass.OBSERVABLE_COUNTERFACTUAL)


def test_forecast_without_ablation_is_not_identifiable():
    rows=tuple(ForecastComponentObservation(observation_id=f"o{i}",target_id="t",horizon_id="h",regime_id="r",component_id="c",component_kind="MODEL",consumed=True,historical_weight=1.0,ensemble_loss=1.0,oof_qualified=True,evidence_class=EvidenceClass.OBSERVABLE_COUNTERFACTUAL) for i in range(3))
    result=attribute_forecast_components(rows,ForecastAttributionPolicy())
    assert result.quality is AttributionQuality.NOT_IDENTIFIABLE


def test_payoff_duplicate_candidate_rejected():
    outcome=CandidateOutcome(candidate_id="a",selected_by_p6=True,observable=True,realized_unit_pnl=1.0,evidence_class=EvidenceClass.FACTUAL_EXECUTED)
    with pytest.raises(ValueError):
        evaluate_payoff_fidelity((),(outcome,outcome),PayoffAttributionPolicy())


def test_payoff_multiple_selected_rejected():
    outcomes=tuple(CandidateOutcome(candidate_id=cid,selected_by_p6=True,observable=True,realized_unit_pnl=1.0,evidence_class=EvidenceClass.FACTUAL_EXECUTED) for cid in ("a","b"))
    with pytest.raises(ValueError):
        evaluate_payoff_fidelity((),outcomes,PayoffAttributionPolicy())


def test_preblocked_candidate_cannot_be_eligible():
    with pytest.raises(ValidationError):
        RankedCandidate(group_id="g",candidate_id="a",predicted_rank=1,predicted_score=1.0,realized_utility=1.0,evidence_class=EvidenceClass.FACTUAL_EXECUTED,eligible=True,pre_blocked=True)


def test_ranking_group_rejects_duplicate_candidates():
    candidate=RankedCandidate(group_id="g",candidate_id="a",predicted_rank=1,predicted_score=1.0,realized_utility=1.0,evidence_class=EvidenceClass.FACTUAL_EXECUTED)
    with pytest.raises(ValidationError):
        RankingGroup(group_id="g",candidates=(candidate,candidate))


def test_prudent_abstention_state():
    candidates=(RankedCandidate(group_id="g",candidate_id="a",predicted_rank=1,predicted_score=1.0,realized_utility=-1.0,evidence_class=EvidenceClass.FACTUAL_EXECUTED),RankedCandidate(group_id="g",candidate_id="b",predicted_rank=2,predicted_score=0.0,realized_utility=-2.0,evidence_class=EvidenceClass.FACTUAL_EXECUTED))
    result=evaluate_ranking((RankingGroup(group_id="g",candidates=candidates,abstained=True),),RankingAttributionPolicy(false_abstention_utility_threshold=0.0))
    assert result.groups[0].abstention_state=="PRUDENT_ABSTENTION"
