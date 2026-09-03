"""P9.S9 competition, promotion recommendation, and typed feedback subphase."""

from .enums import (
    ChallengerQualificationState,
    ChangeOrigin,
    EvidenceQuality,
    FeedbackEffectType,
    FeedbackPhase,
    FeedbackValidationState,
)
from .m01_competition_objective_policy import build_competition_objective_policy
from .m02_robust_configuration_frontier import build_robust_configuration_frontier
from .m03_leaderboard_information_budget import assess_leaderboard_information_budget
from .m04_champion_challenger_qualification import qualify_champion_challengers
from .m05_promotion_recommendation import build_promotion_recommendation
from .m06_typed_feedback_builder import build_typed_feedback
from .m07_feedback_activation_gate import validate_feedback_for_future_activation
from .models import (
    ChampionChallengerQualificationReport,
    CompetitionObjectiveSpec,
    CycleRef,
    FeedbackActivationLedgerEntry,
    FrontierBuildPolicy,
    LeaderboardPolicy,
    NumericChangeBounds,
    RootCauseEvidence,
    SubmissionRecord,
)
from .service import run_s9_subphase

__all__ = [
    "ChampionChallengerQualificationReport",
    "ChallengerQualificationState",
    "ChangeOrigin",
    "CompetitionObjectiveSpec",
    "CycleRef",
    "EvidenceQuality",
    "FeedbackActivationLedgerEntry",
    "FeedbackEffectType",
    "FeedbackPhase",
    "FeedbackValidationState",
    "FrontierBuildPolicy",
    "LeaderboardPolicy",
    "NumericChangeBounds",
    "RootCauseEvidence",
    "SubmissionRecord",
    "assess_leaderboard_information_budget",
    "build_competition_objective_policy",
    "build_promotion_recommendation",
    "build_robust_configuration_frontier",
    "build_typed_feedback",
    "qualify_champion_challengers",
    "run_s9_subphase",
    "validate_feedback_for_future_activation",
]

__version__ = "0.1.0rc1"
