from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import EvidenceClass
from quant_pipeline.phase_09.subphases.s08_attribution.contracts import AttributionQuality
from quant_pipeline.phase_09.subphases.s08_attribution.m03_ranking_attribution import RankedCandidate, RankingAttributionPolicy, RankingGroup, evaluate_ranking


def _candidate(cid, rank, utility, dominates=()):
    return RankedCandidate(group_id="g", candidate_id=cid, predicted_rank=rank, predicted_score=float(10-rank), realized_utility=utility, evidence_class=EvidenceClass.FACTUAL_EXECUTED, dominates_candidate_ids=dominates)


def test_perfect_ranking():
    result=evaluate_ranking((RankingGroup(group_id="g", candidates=(_candidate("a",1,3.0,("b",)), _candidate("b",2,1.0))),), RankingAttributionPolicy())
    group=result.groups[0]
    assert group.pairwise_accuracy == 1.0
    assert group.ndcg_at_k == 1.0
    assert group.ranking_regret == 0.0


def test_inverted_ranking_has_regret():
    result=evaluate_ranking((RankingGroup(group_id="g", candidates=(_candidate("a",2,3.0), _candidate("b",1,1.0))),), RankingAttributionPolicy())
    assert result.groups[0].pairwise_accuracy == 0.0
    assert result.total_ranking_regret == 2.0


def test_false_abstention_is_separate_state():
    group=RankingGroup(group_id="g", candidates=(_candidate("a",1,2.0), _candidate("b",2,0.0)), abstained=True)
    result=evaluate_ranking((group,), RankingAttributionPolicy(false_abstention_utility_threshold=0.5))
    assert result.groups[0].abstention_state == "FALSE_ABSTENTION"


def test_insufficient_observable_candidates():
    candidate=_candidate("a",1,1.0).model_copy(update={"realized_utility":None})
    result=evaluate_ranking((RankingGroup(group_id="g", candidates=(candidate,)),), RankingAttributionPolicy())
    assert result.quality is AttributionQuality.INSUFFICIENT_EVIDENCE
