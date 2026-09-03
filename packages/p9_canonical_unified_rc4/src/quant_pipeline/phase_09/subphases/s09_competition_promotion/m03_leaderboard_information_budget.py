from __future__ import annotations

from datetime import datetime

from .enums import ChangeOrigin, ContaminationState, LeaderboardState, ModuleStatus
from .models.common import ModuleDiagnostics, ModuleResult, build_module_result
from .models.leaderboard import (
    LeaderboardInformationBudgetReport,
    LeaderboardPolicy,
    SubmissionAssessment,
    SubmissionEligibilityReceipt,
    SubmissionRecord,
)

MODULE_ID = "P9.S9.M03"


def _submission_cost(
    record: SubmissionRecord,
    policy: LeaderboardPolicy,
) -> tuple[float, list[str]]:
    cost = policy.base_submission_cost
    reasons: list[str] = []
    if record.hypothesis_committed_at is None:
        cost += policy.uncommitted_penalty
        reasons.append("submission lacks a precommitted hypothesis")
    magnitude = sum(change.normalized_magnitude for change in record.changes_after_parent)
    cost += policy.change_magnitude_weight * magnitude
    reacted_to_public_score = any(
        change.origin == ChangeOrigin.PUBLIC_SCORE_REACTION
        for change in record.changes_after_parent
    )
    if reacted_to_public_score:
        cost += policy.public_reaction_penalty
        reasons.append("configuration changed in reaction to public leaderboard score")
    if any(change.origin == ChangeOrigin.UNKNOWN for change in record.changes_after_parent):
        reasons.append("change origin is unknown")
    return cost, reasons


def assess_leaderboard_information_budget(
    *,
    submission_ledger: tuple[SubmissionRecord, ...],
    policy: LeaderboardPolicy,
    candidate_configuration_id: str,
) -> tuple[ModuleResult[LeaderboardInformationBudgetReport], SubmissionEligibilityReceipt]:
    """Assess adaptive information extraction from the public leaderboard."""

    ordered = tuple(
        sorted(
            submission_ledger,
            key=lambda item: (item.submitted_at, item.submission_id),
        )
    )
    ids = [record.submission_id for record in ordered]
    if len(set(ids)) != len(ids):
        report = LeaderboardInformationBudgetReport(
            state=LeaderboardState.SUBMISSION_HISTORY_INCOMPLETE,
            policy_id=policy.policy_id,
            submission_count=len(ordered),
            total_information_cost=0.0,
            remaining_information_budget=policy.information_budget,
            assessments=(),
            full_promotion_eligible=False,
        )
        result = build_module_result(
            module_id=MODULE_ID,
            status=ModuleStatus.INVALID,
            output=report,
            reason_codes=("P9_LEADERBOARD_DUPLICATE_SUBMISSION_ID",),
            diagnostics=ModuleDiagnostics(warnings=("duplicate submission IDs detected",)),
        )
        receipt = SubmissionEligibilityReceipt(
            configuration_id=candidate_configuration_id,
            eligible_for_submission=False,
            eligible_for_full_promotion=False,
            leaderboard_state=report.state,
            reasons=("submission history invalid",),
        )
        return result, receipt

    seen: set[str] = set()
    cumulative = 0.0
    assessments: list[SubmissionAssessment] = []
    history_incomplete = False
    max_state = ContaminationState.CLEAN
    for record in ordered:
        reasons: list[str] = []
        if record.parent_submission_id is not None and record.parent_submission_id not in seen:
            history_incomplete = True
            reasons.append("parent submission missing or appears after child")
        cost, cost_reasons = _submission_cost(record, policy)
        reasons.extend(cost_reasons)
        cumulative += cost
        if cumulative >= policy.contamination_threshold or any(
            change.origin == ChangeOrigin.PUBLIC_SCORE_REACTION
            for change in record.changes_after_parent
        ):
            state = ContaminationState.CONTAMINATED
            max_state = ContaminationState.CONTAMINATED
        elif cumulative >= policy.limited_use_threshold or record.hypothesis_committed_at is None:
            state = ContaminationState.LIMITED_USE
            if max_state == ContaminationState.CLEAN:
                max_state = ContaminationState.LIMITED_USE
        else:
            state = ContaminationState.CLEAN
        assessments.append(
            SubmissionAssessment(
                submission_id=record.submission_id,
                information_cost=cost,
                cumulative_information_cost=cumulative,
                contamination_state=state,
                reasons=tuple(reasons),
            )
        )
        seen.add(record.submission_id)

    if history_incomplete:
        leaderboard_state = LeaderboardState.SUBMISSION_HISTORY_INCOMPLETE
    elif len(ordered) >= policy.maximum_submissions or cumulative >= policy.information_budget:
        leaderboard_state = LeaderboardState.SUBMISSION_BUDGET_EXHAUSTED
    elif max_state == ContaminationState.CONTAMINATED:
        leaderboard_state = LeaderboardState.LEADERBOARD_CONTAMINATED
    elif max_state == ContaminationState.LIMITED_USE:
        leaderboard_state = LeaderboardState.LEADERBOARD_LIMITED_USE
    else:
        leaderboard_state = LeaderboardState.LEADERBOARD_CLEAN

    full_promotion_eligible = leaderboard_state == LeaderboardState.LEADERBOARD_CLEAN
    remaining = max(0.0, policy.information_budget - cumulative)
    report = LeaderboardInformationBudgetReport(
        state=leaderboard_state,
        policy_id=policy.policy_id,
        submission_count=len(ordered),
        total_information_cost=cumulative,
        remaining_information_budget=remaining,
        assessments=tuple(assessments),
        full_promotion_eligible=full_promotion_eligible,
    )
    can_submit = (
        leaderboard_state
        not in {
            LeaderboardState.SUBMISSION_BUDGET_EXHAUSTED,
            LeaderboardState.SUBMISSION_HISTORY_INCOMPLETE,
        }
        and len(ordered) < policy.maximum_submissions
        and remaining >= policy.base_submission_cost
    )
    reasons = []
    if not can_submit:
        reasons.append("submission budget or history gate blocks another submission")
    if not full_promotion_eligible:
        reasons.append("leaderboard evidence cannot support full promotion")
    receipt = SubmissionEligibilityReceipt(
        configuration_id=candidate_configuration_id,
        eligible_for_submission=can_submit,
        eligible_for_full_promotion=full_promotion_eligible,
        leaderboard_state=leaderboard_state,
        reasons=tuple(reasons),
    )
    status = (
        ModuleStatus.INVALID
        if leaderboard_state == LeaderboardState.SUBMISSION_HISTORY_INCOMPLETE
        else ModuleStatus.SUCCESS
    )
    reason_codes = (
        ("P9_LEADERBOARD_SUBMISSION_HISTORY_INCOMPLETE",)
        if leaderboard_state == LeaderboardState.SUBMISSION_HISTORY_INCOMPLETE
        else ()
    )
    result = build_module_result(
        module_id=MODULE_ID,
        status=status,
        output=report,
        reason_codes=reason_codes,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("submission_count", len(ordered)),
                (
                    "public_score_reaction_count",
                    sum(
                        change.origin == ChangeOrigin.PUBLIC_SCORE_REACTION
                        for record in ordered
                        for change in record.changes_after_parent
                    ),
                ),
            ),
            trace=("submission history assessed as append-only adaptive holdout usage",),
        ),
    )
    return result, receipt
