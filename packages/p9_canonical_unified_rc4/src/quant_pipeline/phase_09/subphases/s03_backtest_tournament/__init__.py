"""P9.S3 — backtest tournament and temporal validation."""

from .m01_temporal_plan import build_temporal_evaluation_plan
from .m02_purged_walk_forward import build_purged_walk_forward_assignments
from .m03_backtest_runner import PhaseRunnerRegistry, execute_trial_plan
from .m04_integrity_replay import qualify_backtest
from .m05_competition_metric import CompetitionMetricRegistry, compute_competition_score
from .m06_score_aggregation import aggregate_scores
from .m07_provisional_mcs import compare_trials
from .service import S3TournamentService

__all__ = [
    "CompetitionMetricRegistry",
    "PhaseRunnerRegistry",
    "aggregate_scores",
    "build_purged_walk_forward_assignments",
    "build_temporal_evaluation_plan",
    "compare_trials",
    "compute_competition_score",
    "execute_trial_plan",
    "qualify_backtest",
    "S3TournamentService",
]
