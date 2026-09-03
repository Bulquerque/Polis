from __future__ import annotations

from .enums import (
    ChallengerQualificationState,
    ContaminationState,
    FrontierState,
    LeaderboardState,
    ModuleStatus,
    ParameterRegionState,
)
from .models.common import ModuleDiagnostics, ModuleResult, build_module_result
from .models.frontier import ConfigurationEvaluationCard, RobustConfigurationFrontier
from .models.leaderboard import LeaderboardInformationBudgetReport
from .models.policy import CompetitionObjectivePolicy
from .models.qualification import (
    ChallengerQualification,
    ChampionChallengerQualificationReport,
    PairwiseComparisonEvidence,
)
from .scoring import configuration_utility, tie_break_key

MODULE_ID = "P9.S9.M04"


def _region_state_for(
    configuration_id: str,
    frontier: RobustConfigurationFrontier,
) -> ParameterRegionState | None:
    for cohort in frontier.cohorts:
        for region in cohort.robust_regions:
            if configuration_id in region.member_configuration_ids:
                return region.state
    return None


def _is_frontier_member(configuration_id: str, frontier: RobustConfigurationFrontier) -> bool:
    return any(configuration_id in cohort.frontier_configuration_ids for cohort in frontier.cohorts)


def _qualification_rank(state: ChallengerQualificationState) -> int:
    order = {
        ChallengerQualificationState.CHALLENGER_QUALIFIED: 7,
        ChallengerQualificationState.CHALLENGER_QUALIFIED_LIMITED_CAPITAL: 6,
        ChallengerQualificationState.CHALLENGER_SHADOW_ONLY: 5,
        ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE: 4,
        ChallengerQualificationState.RETAIN_CHAMPION: 3,
        ChallengerQualificationState.INSUFFICIENT_EVIDENCE: 2,
        ChallengerQualificationState.QUARANTINE_CHALLENGER: 1,
        ChallengerQualificationState.COMPARISON_INVALID: 0,
    }
    return order[state]


def qualify_champion_challengers(
    *,
    objective: CompetitionObjectivePolicy,
    frontier: RobustConfigurationFrontier,
    leaderboard: LeaderboardInformationBudgetReport,
    configurations: tuple[ConfigurationEvaluationCard, ...],
    champion_configuration_id: str,
    challenger_configuration_ids: tuple[str, ...],
    pairwise_evidence: tuple[PairwiseComparisonEvidence, ...],
) -> ModuleResult[ChampionChallengerQualificationReport]:
    """Qualify challengers against the champion using paired, stress, and live evidence."""

    cards = {card.configuration_id: card for card in configurations}
    champion = cards[champion_configuration_id]
    evidence_by_challenger = {
        evidence.challenger_configuration_id: evidence
        for evidence in pairwise_evidence
        if evidence.champion_configuration_id == champion_configuration_id
    }
    qualifications: list[ChallengerQualification] = []

    for challenger_id in sorted(challenger_configuration_ids):
        challenger = cards[challenger_id]
        evidence = evidence_by_challenger.get(challenger_id)
        blocking: list[str] = []
        limitations: list[str] = []
        state = ChallengerQualificationState.INSUFFICIENT_EVIDENCE
        contamination = challenger.contamination_state

        if challenger.cohort_id != champion.cohort_id:
            state = ChallengerQualificationState.COMPARISON_INVALID
            blocking.append("champion and challenger cohorts differ")
        elif evidence is None:
            state = ChallengerQualificationState.INSUFFICIENT_EVIDENCE
            blocking.append("paired comparison evidence is missing")
        elif evidence.cohort_id != challenger.cohort_id:
            state = ChallengerQualificationState.COMPARISON_INVALID
            blocking.append("pairwise evidence cohort does not match configuration cohort")
        elif challenger.live_degradation_detected or evidence.live_degradation_detected:
            state = ChallengerQualificationState.QUARANTINE_CHALLENGER
            blocking.append("prospective live or shadow degradation detected")
        elif challenger.critical_regime_failures:
            state = ChallengerQualificationState.RETAIN_CHAMPION
            blocking.append("challenger fails one or more critical regimes")
        elif not challenger.stress_resilient:
            state = ChallengerQualificationState.QUARANTINE_CHALLENGER
            blocking.append("challenger is structurally stress-fragile")
        elif not _is_frontier_member(challenger_id, frontier):
            state = ChallengerQualificationState.RETAIN_CHAMPION
            blocking.append("challenger is not on the committed robust frontier")
        elif evidence.effect_size < objective.minimum_effect_size:
            state = ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE
            limitations.append("economic effect is below the committed minimum")
        elif evidence.probability_of_superiority < objective.minimum_probability_of_superiority:
            state = ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE
            limitations.append("probability of superiority is below policy threshold")
        elif evidence.effect_lower_bound <= 0.0:
            state = ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE
            limitations.append("paired lower bound does not establish positive superiority")
        else:
            complexity_increase = max(0.0, challenger.complexity_score - champion.complexity_score)
            if (
                complexity_increase
                > objective.maximum_complexity_increase_without_material_gain
                and evidence.effect_size < 2.0 * objective.minimum_effect_size
            ):
                state = ChallengerQualificationState.RETAIN_CHAMPION
                blocking.append("complexity increase is not justified by material gain")
            elif leaderboard.state == LeaderboardState.LEADERBOARD_CONTAMINATED:
                state = ChallengerQualificationState.CHALLENGER_SHADOW_ONLY
                limitations.append("leaderboard contamination blocks capital promotion")
            elif leaderboard.state == LeaderboardState.LEADERBOARD_LIMITED_USE:
                state = ChallengerQualificationState.CHALLENGER_QUALIFIED_LIMITED_CAPITAL
                limitations.append("leaderboard use limits the initial deployment stage")
            elif not challenger.capacity_feasible:
                state = ChallengerQualificationState.CHALLENGER_SHADOW_ONLY
                limitations.append("capacity evidence is not sufficient for capital deployment")
            elif not challenger.live_evidence_available:
                state = ChallengerQualificationState.CHALLENGER_SHADOW_ONLY
                limitations.append("prospective evidence is not yet available")
            elif _region_state_for(challenger_id, frontier) != ParameterRegionState.ROBUST_PLATEAU:
                state = ChallengerQualificationState.CHALLENGER_QUALIFIED_LIMITED_CAPITAL
                limitations.append("parameter region is not a robust plateau")
            else:
                state = ChallengerQualificationState.CHALLENGER_QUALIFIED

        qualifications.append(
            ChallengerQualification(
                challenger_configuration_id=challenger_id,
                state=state,
                effect_size=None if evidence is None else evidence.effect_size,
                probability_of_superiority=(
                    None if evidence is None else evidence.probability_of_superiority
                ),
                contamination_state=contamination,
                blocking_reasons=tuple(blocking),
                limitations=tuple(limitations),
                evidence_refs=() if evidence is None else evidence.evidence_refs,
            )
        )

    candidates = [
        item
        for item in qualifications
        if item.state
        in {
            ChallengerQualificationState.CHALLENGER_QUALIFIED,
            ChallengerQualificationState.CHALLENGER_QUALIFIED_LIMITED_CAPITAL,
            ChallengerQualificationState.CHALLENGER_SHADOW_ONLY,
        }
    ]
    recommended: str | None = None
    if candidates:
        candidates.sort(
            key=lambda item: (
                _qualification_rank(item.state),
                configuration_utility(cards[item.challenger_configuration_id], objective),
                tie_break_key(cards[item.challenger_configuration_id].metric_map(), objective),
                item.challenger_configuration_id,
            ),
            reverse=True,
        )
        recommended = candidates[0].challenger_configuration_id
        report_state = candidates[0].state
    elif any(
        item.state == ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE
        for item in qualifications
    ):
        report_state = ChallengerQualificationState.STATISTICALLY_INDISTINGUISHABLE
    elif any(
        item.state == ChallengerQualificationState.COMPARISON_INVALID
        for item in qualifications
    ):
        report_state = ChallengerQualificationState.COMPARISON_INVALID
    elif any(
        item.state == ChallengerQualificationState.INSUFFICIENT_EVIDENCE
        for item in qualifications
    ):
        report_state = ChallengerQualificationState.INSUFFICIENT_EVIDENCE
    elif any(
        item.state == ChallengerQualificationState.QUARANTINE_CHALLENGER
        for item in qualifications
    ):
        report_state = ChallengerQualificationState.QUARANTINE_CHALLENGER
    else:
        report_state = ChallengerQualificationState.RETAIN_CHAMPION

    report = ChampionChallengerQualificationReport(
        champion_configuration_id=champion_configuration_id,
        cohort_id=champion.cohort_id,
        qualifications=tuple(qualifications),
        recommended_challenger_id=recommended,
        report_state=report_state,
        warnings=(
            ("frontier lacks eligible configurations",)
            if frontier.state == FrontierState.NO_ELIGIBLE_CONFIGURATION
            else ()
        ),
    )
    status = (
        ModuleStatus.INVALID
        if report_state == ChallengerQualificationState.COMPARISON_INVALID
        else ModuleStatus.INSUFFICIENT_EVIDENCE
        if report_state == ChallengerQualificationState.INSUFFICIENT_EVIDENCE
        else ModuleStatus.SUCCESS
    )
    reason_codes = (
        ("P9_PROMOTION_CHAMPION_CHALLENGER_COMPARISON_INVALID",)
        if status == ModuleStatus.INVALID
        else ("P9_PROMOTION_INSUFFICIENT_EVIDENCE",)
        if status == ModuleStatus.INSUFFICIENT_EVIDENCE
        else ()
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=report,
        reason_codes=reason_codes,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("challenger_count", len(challenger_configuration_ids)),
                ("qualified_count", len(candidates)),
            ),
            trace=("champion and challengers compared on paired evidence and committed gates",),
        ),
    )
