"""P9.S3.M01 — temporal evaluation plan builder."""

from __future__ import annotations

from datetime import timedelta

from .common import content_sha256
from .errors import TemporalIntegrityError
from .reason_codes import ReasonCode
from .temporal_models import (
    FoldDefinition,
    HoldoutFirewallPolicy,
    TemporalEvaluationPlan,
    TemporalPlanPolicy,
    TimeWindow,
    WindowMode,
)


def build_temporal_evaluation_plan(policy: TemporalPlanPolicy) -> TemporalEvaluationPlan:
    """Build deterministic nested walk-forward folds and reserve the final holdout.

    The function operates in calendar time. It never infers a gap from sample counts.
    """

    holdout_start = policy.dataset_window.end - policy.holdout.as_timedelta()
    if holdout_start <= policy.dataset_window.start:
        raise TemporalIntegrityError(ReasonCode.TEMPORAL_PLAN_INFEASIBLE.value)

    first_tuning_start = policy.dataset_window.start + policy.initial_train.as_timedelta()
    first_test_start = (
        first_tuning_start
        + policy.embargo.as_timedelta()
        + policy.tuning.as_timedelta()
        + policy.embargo.as_timedelta()
    )
    current_test_start = first_test_start
    folds: list[FoldDefinition] = []
    outer_index = 0

    while current_test_start + policy.test.as_timedelta() <= holdout_start:
        tuning_end = current_test_start - policy.embargo.as_timedelta()
        tuning_start = tuning_end - policy.tuning.as_timedelta()
        train_end = tuning_start - policy.embargo.as_timedelta()
        if policy.window_mode is WindowMode.EXPANDING:
            train_start = policy.dataset_window.start
        else:
            if policy.max_train is None:
                raise ContractError("rolling temporal policy requires max_train")
            train_start = max(
                policy.dataset_window.start,
                train_end - policy.max_train.as_timedelta(),
            )

        if train_end - train_start < policy.initial_train.as_timedelta():
            current_test_start += policy.step.as_timedelta()
            continue

        fold = FoldDefinition(
            fold_id=f"outer_{outer_index:03d}",
            outer_index=outer_index,
            train_window=TimeWindow(start=train_start, end=train_end),
            tuning_window=TimeWindow(start=tuning_start, end=tuning_end),
            test_window=TimeWindow(
                start=current_test_start,
                end=current_test_start + policy.test.as_timedelta(),
            ),
            embargo=policy.embargo,
        )
        folds.append(fold)
        outer_index += 1
        current_test_start += policy.step.as_timedelta()

    if len(folds) < policy.minimum_outer_folds:
        raise TemporalIntegrityError(
            f"{ReasonCode.TEMPORAL_PLAN_INFEASIBLE.value}: generated={len(folds)} "
            f"required={policy.minimum_outer_folds}"
        )

    holdout = HoldoutFirewallPolicy(
        holdout_window=TimeWindow(start=holdout_start, end=policy.dataset_window.end),
        access_policy_id=f"{policy.policy_id}:holdout_firewall",
    )
    policy_hash = content_sha256(policy)
    body = {
        "policy_id": policy.policy_id,
        "policy_sha256": policy_hash,
        "folds": folds,
        "holdout": holdout,
    }
    digest = content_sha256(body)
    return TemporalEvaluationPlan(
        plan_id=f"temporal_plan:{digest[:16]}",
        policy_id=policy.policy_id,
        policy_sha256=policy_hash,
        folds=tuple(folds),
        holdout_firewall=holdout,
        content_sha256=digest,
    )
