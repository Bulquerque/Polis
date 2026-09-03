from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import rankdata, spearmanr

from .contracts import S5State
from .m03_time_series_block_bootstrap_engine import _stationary_indices
from .models import (
    BacktestRobustnessQualificationReport,
    MultipleTestingResult,
    PBOResult,
    RobustnessQualificationRequest,
)
from .numerics import to_float_matrix
from .randomness import derive_generator

MODULE_ID = "P9.S5.M08"


@dataclass(slots=True)
class _EvidenceAccumulator:
    favorable: list[str] = field(default_factory=list)
    contrary: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    hard_invalid: bool = False
    overfit: bool = False
    fragile: bool = False
    unresolved: bool = False


def _score_columns(matrix: np.ndarray) -> np.ndarray:
    means = np.mean(matrix, axis=0)
    deviations = np.std(matrix, axis=0, ddof=1)
    scores = np.full(matrix.shape[1], -np.inf, dtype=np.float64)
    valid = deviations > np.finfo(np.float64).eps
    scores[valid] = means[valid] / deviations[valid]
    scores[~valid & (means > 0)] = np.inf
    return scores


def _cscv_combinations(
    request: RobustnessQualificationRequest,
    slices: int,
) -> list[tuple[int, ...]]:
    combinations = list(itertools.combinations(range(slices), slices // 2))
    limit = request.multiple_testing_policy.maximum_cscv_combinations
    if len(combinations) <= limit:
        return combinations
    rng = derive_generator(
        request.seed_policy,
        request.context.experiment_id,
        MODULE_ID,
        "CSCV",
    )
    selected = rng.choice(len(combinations), size=limit, replace=False)
    return [combinations[int(index)] for index in sorted(selected)]


def _cscv_pbo(request: RobustnessQualificationRequest) -> tuple[PBOResult, float | None]:
    matrix = to_float_matrix(request.trial_performance.performance_values)
    nobs, n_trials = matrix.shape
    slices = request.multiple_testing_policy.cscv_slices
    if n_trials < 2 or nobs < slices * 2:
        return _pbo_not_applicable(), None

    partitions = [
        np.asarray(part, dtype=np.int64)
        for part in np.array_split(np.arange(nobs), slices)
    ]
    combinations = _cscv_combinations(request, slices)
    logits: list[float] = []
    stability_values: list[float] = []
    all_indices = set(range(slices))
    for selected_slices in combinations:
        train_index = np.concatenate([partitions[index] for index in selected_slices])
        test_slices = sorted(all_indices.difference(selected_slices))
        test_index = np.concatenate([partitions[index] for index in test_slices])
        train_scores = _score_columns(matrix[train_index])
        test_scores = _score_columns(matrix[test_index])
        winner = int(np.argmax(train_scores))
        ranks = rankdata(test_scores, method="average")
        percentile = float((ranks[winner] - 1.0) / max(n_trials - 1.0, 1.0))
        clipped = float(np.clip(percentile, 1e-12, 1.0 - 1e-12))
        logits.append(math.log(clipped / (1.0 - clipped)))
        correlation = spearmanr(train_scores, test_scores).statistic
        if np.isfinite(correlation):
            stability_values.append((float(correlation) + 1.0) / 2.0)
    if not logits:
        return _pbo_not_applicable(), None
    pbo = float(np.mean(np.asarray(logits) <= 0.0))
    rank_stability = float(np.mean(stability_values)) if stability_values else None
    return (
        PBOResult(
            applicable=True,
            pbo=pbo,
            combination_count=len(logits),
            logits=tuple(logits),
        ),
        rank_stability,
    )


def _pbo_not_applicable() -> PBOResult:
    return PBOResult(
        applicable=False,
        pbo=None,
        combination_count=0,
        logits=(),
        reason_codes=("P9_OVERFIT_PBO_NOT_APPLICABLE",),
    )


def _reality_check(request: RobustnessQualificationRequest) -> MultipleTestingResult:
    matrix = to_float_matrix(request.trial_performance.performance_values)
    nobs, n_trials = matrix.shape
    if n_trials < 2 or nobs < 20:
        return MultipleTestingResult(
            applicable=False,
            reality_check_statistic=None,
            reality_check_pvalue=None,
            tested_trial_count=n_trials,
            reason_codes=("P9_OVERFIT_REALITY_CHECK_NOT_APPLICABLE",),
        )
    means = np.mean(matrix, axis=0)
    observed = float(math.sqrt(nobs) * np.max(means))
    centered = matrix - means
    block_length = min(request.multiple_testing_policy.reality_check_block_length, nobs)
    rng = derive_generator(
        request.seed_policy,
        request.context.experiment_id,
        MODULE_ID,
        "REALITY_CHECK",
    )
    statistics = np.empty(
        request.multiple_testing_policy.reality_check_replicates,
        dtype=np.float64,
    )
    for replicate in range(statistics.size):
        indices = _stationary_indices(nobs, block_length, rng)
        statistics[replicate] = math.sqrt(nobs) * float(
            np.max(np.mean(centered[indices], axis=0))
        )
    pvalue = float((1.0 + np.sum(statistics >= observed)) / (statistics.size + 1.0))
    return MultipleTestingResult(
        applicable=True,
        reality_check_statistic=observed,
        reality_check_pvalue=pvalue,
        tested_trial_count=n_trials,
    )


def _missing_metric_report(
    request: RobustnessQualificationRequest,
) -> BacktestRobustnessQualificationReport:
    code = "P9_OVERFIT_TARGET_METRIC_MISSING"
    return BacktestRobustnessQualificationReport(
        status=S5State.INVALID,
        target_configuration_id=request.target_configuration_id,
        target_metric_id=request.target_metric_id,
        pbo=PBOResult(
            applicable=False,
            pbo=None,
            combination_count=0,
            logits=(),
            reason_codes=(code,),
        ),
        multiple_testing=MultipleTestingResult(
            applicable=False,
            reality_check_statistic=None,
            reality_check_pvalue=None,
            tested_trial_count=0,
            reason_codes=(code,),
        ),
        dsr=request.sharpe_inference.deflated_sharpe_ratio,
        bootstrap_lower_bound=None,
        probability_above_threshold=None,
        worst_fold_score=None,
        rank_stability=None,
        favorable_evidence=(),
        contrary_evidence=("target metric is absent",),
        reason_codes=(code,),
        limitations=(),
    )


def _binding_failure_report(
    request: RobustnessQualificationRequest,
    code: str,
    message: str,
) -> BacktestRobustnessQualificationReport:
    return BacktestRobustnessQualificationReport(
        status=S5State.INVALID,
        target_configuration_id=request.target_configuration_id,
        target_metric_id=request.target_metric_id,
        pbo=PBOResult(
            applicable=False,
            pbo=None,
            combination_count=0,
            logits=(),
            reason_codes=(code,),
        ),
        multiple_testing=MultipleTestingResult(
            applicable=False,
            reality_check_statistic=None,
            reality_check_pvalue=None,
            tested_trial_count=0,
            reason_codes=(code,),
        ),
        dsr=request.sharpe_inference.deflated_sharpe_ratio,
        bootstrap_lower_bound=None,
        probability_above_threshold=None,
        worst_fold_score=None,
        rank_stability=None,
        favorable_evidence=(),
        contrary_evidence=(message,),
        reason_codes=(code,),
        limitations=(),
    )


def _evaluate_trial_family(
    request: RobustnessQualificationRequest,
    evidence: _EvidenceAccumulator,
) -> None:
    if request.trial_performance.family_complete:
        return
    evidence.unresolved = True
    evidence.contrary.append("trial family is incomplete")
    evidence.reasons.append("P9_OVERFIT_TRIAL_FAMILY_INCOMPLETE")


def _evaluate_pbo(
    request: RobustnessQualificationRequest,
    result: PBOResult,
    evidence: _EvidenceAccumulator,
) -> None:
    if not result.applicable or result.pbo is None:
        evidence.unresolved = True
        evidence.limitations.append("PBO was not applicable")
        return
    if result.pbo > request.threshold_policy.maximum_pbo:
        evidence.overfit = True
        evidence.contrary.append("PBO exceeds the maximum policy threshold")
        evidence.reasons.append("P9_OVERFIT_PBO_HIGH")
        return
    evidence.favorable.append("PBO is below the maximum policy threshold")


def _evaluate_dsr(
    request: RobustnessQualificationRequest,
    dsr: float | None,
    evidence: _EvidenceAccumulator,
) -> None:
    if dsr is None:
        evidence.unresolved = True
        evidence.limitations.append("DSR is unavailable")
        evidence.reasons.append("P9_OVERFIT_DSR_NOT_IDENTIFIABLE")
        return
    if dsr < request.threshold_policy.minimum_dsr:
        evidence.overfit = True
        evidence.contrary.append("DSR is below the minimum policy threshold")
        evidence.reasons.append("P9_OVERFIT_DSR_BELOW_POLICY")
        return
    evidence.favorable.append("DSR meets the minimum policy threshold")


def _evaluate_fold(
    request: RobustnessQualificationRequest,
    worst_fold: float | None,
    evidence: _EvidenceAccumulator,
) -> None:
    if worst_fold is None:
        evidence.hard_invalid = True
        evidence.contrary.append("fold scores do not match the target configuration")
        evidence.reasons.append("P9_OVERFIT_COHORT_MISMATCH")
        return
    if worst_fold < request.threshold_policy.minimum_worst_fold_score:
        evidence.fragile = True
        evidence.contrary.append("worst fold is below the policy threshold")
        evidence.reasons.append("P9_OVERFIT_WORST_FOLD_FAILURE")
        return
    evidence.favorable.append("worst fold meets the policy threshold")


def _evaluate_bootstrap_probability(
    request: RobustnessQualificationRequest,
    probability: float | None,
    evidence: _EvidenceAccumulator,
) -> None:
    if probability is None:
        evidence.unresolved = True
        evidence.limitations.append("bootstrap probability above threshold is unavailable")
        return
    threshold = request.threshold_policy.minimum_bootstrap_probability_above_threshold
    if probability < threshold:
        evidence.fragile = True
        evidence.contrary.append("bootstrap probability above threshold is too low")
        evidence.reasons.append("P9_OVERFIT_BOOTSTRAP_PROBABILITY_LOW")
        return
    evidence.favorable.append("bootstrap probability above threshold is acceptable")


def _evaluate_rank_stability(
    request: RobustnessQualificationRequest,
    rank_stability: float | None,
    evidence: _EvidenceAccumulator,
) -> None:
    if rank_stability is None:
        evidence.unresolved = True
        evidence.limitations.append("rank stability is unavailable")
        return
    if rank_stability < request.threshold_policy.minimum_rank_stability:
        evidence.fragile = True
        evidence.contrary.append("rank stability is below threshold")
        evidence.reasons.append("P9_OVERFIT_RANK_INSTABILITY")
        return
    evidence.favorable.append("rank stability is acceptable")


def _evaluate_multiple_testing(
    request: RobustnessQualificationRequest,
    result: MultipleTestingResult,
    evidence: _EvidenceAccumulator,
) -> None:
    if not result.applicable or result.reality_check_pvalue is None:
        evidence.unresolved = True
        evidence.limitations.append("multiple-testing Reality Check was not applicable")
        return
    if result.reality_check_pvalue > request.threshold_policy.maximum_reality_check_pvalue:
        evidence.overfit = True
        evidence.contrary.append("Reality Check does not reject the no-superiority null")
        evidence.reasons.append("P9_OVERFIT_MULTIPLE_TESTING_UNRESOLVED")
        return
    evidence.favorable.append("Reality Check supports superior performance")


def _resolve_status(evidence: _EvidenceAccumulator) -> S5State:
    if evidence.hard_invalid:
        return S5State.INVALID
    if evidence.overfit:
        return S5State.BACKTEST_OVERFIT_RISK
    if evidence.fragile:
        return S5State.FRAGILE
    if evidence.unresolved:
        return S5State.SELECTION_BIAS_UNRESOLVED
    return S5State.ROBUST


def qualify_backtest(
    request: RobustnessQualificationRequest,
) -> BacktestRobustnessQualificationReport:
    """Combine non-compensable statistical evidence into an S5 qualification."""

    if request.target_configuration_id != request.context.configuration_id:
        return _binding_failure_report(
            request,
            "P9_OVERFIT_TARGET_CONFIGURATION_CONTEXT_MISMATCH",
            "target configuration differs from the run context",
        )
    if request.target_configuration_id not in request.trial_performance.configuration_ids:
        return _binding_failure_report(
            request,
            "P9_OVERFIT_TARGET_CONFIGURATION_TRIAL_FAMILY_MISMATCH",
            "target configuration is absent from the trial family",
        )
    sharpe_configuration = request.sharpe_inference.target_configuration_id
    if (
        sharpe_configuration is not None
        and sharpe_configuration != request.target_configuration_id
    ):
        return _binding_failure_report(
            request,
            "P9_OVERFIT_SHARPE_CONFIGURATION_MISMATCH",
            "Sharpe inference belongs to a different configuration",
        )
    target_estimate = next(
        (
            item
            for item in request.metric_distributions.estimates
            if item.metric_id == request.target_metric_id
        ),
        None,
    )
    if target_estimate is None:
        return _missing_metric_report(request)

    pbo_result, rank_stability = _cscv_pbo(request)
    multiple_testing = _reality_check(request)
    worst_fold = (
        min((item.score for item in request.fold_scores.scores), default=None)
        if request.fold_scores.configuration_id == request.target_configuration_id
        else None
    )
    dsr = request.sharpe_inference.deflated_sharpe_ratio
    probability = target_estimate.probability_above_threshold
    evidence = _EvidenceAccumulator()
    _evaluate_trial_family(request, evidence)
    _evaluate_pbo(request, pbo_result, evidence)
    _evaluate_dsr(request, dsr, evidence)
    _evaluate_fold(request, worst_fold, evidence)
    _evaluate_bootstrap_probability(request, probability, evidence)
    _evaluate_rank_stability(request, rank_stability, evidence)
    _evaluate_multiple_testing(request, multiple_testing, evidence)

    return BacktestRobustnessQualificationReport(
        status=_resolve_status(evidence),
        target_configuration_id=request.target_configuration_id,
        target_metric_id=request.target_metric_id,
        pbo=pbo_result,
        multiple_testing=multiple_testing,
        dsr=dsr,
        bootstrap_lower_bound=target_estimate.lower_confidence_bound,
        probability_above_threshold=probability,
        worst_fold_score=worst_fold,
        rank_stability=rank_stability,
        favorable_evidence=tuple(evidence.favorable),
        contrary_evidence=tuple(evidence.contrary),
        reason_codes=tuple(dict.fromkeys(evidence.reasons)),
        limitations=tuple(evidence.limitations),
    )
