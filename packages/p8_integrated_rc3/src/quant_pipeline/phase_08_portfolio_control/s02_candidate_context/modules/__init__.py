
"""S2 module entrypoints."""

from .m01_candidate_intent_normalizer import run_m01
from .m02_shared_exposure_graph_builder import run_m02
from .m03_payoff_redundancy_and_equivalence_grouper import run_m03
from .m04_leg_level_canonicalization_and_netting_engine import run_m04
from .m05_admissible_portfolio_action_universe_builder import run_m05
from .m06_p7_ordinal_preference_compiler import run_m06

__all__ = ["run_m01", "run_m02", "run_m03", "run_m04", "run_m05", "run_m06"]
