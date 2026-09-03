"""P9.S5 dependent bootstrap, inference and overfitting qualification."""

from .m01_dependence_and_sampling_diagnostics import diagnose_dependence
from .m02_automatic_block_length_selector import select_block_length
from .m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from .m04_hierarchical_portfolio_bootstrap_engine import evaluate_hierarchical_bootstrap
from .m05_trade_and_execution_resampling_engine import resample_trade_episodes
from .m06_bootstrap_metric_distribution_builder import build_metric_distributions
from .m07_sharpe_inference_and_deflation_engine import infer_sharpe
from .m08_backtest_overfitting_multiple_testing_qualification_gate import qualify_backtest
from .models import S5OutputBundle, S5RunRequest
from .runner import run_s5

__all__ = [
    "S5OutputBundle",
    "S5RunRequest",
    "build_metric_distributions",
    "diagnose_dependence",
    "evaluate_hierarchical_bootstrap",
    "generate_bootstrap_indices",
    "infer_sharpe",
    "qualify_backtest",
    "resample_trade_episodes",
    "run_s5",
    "select_block_length",
]
