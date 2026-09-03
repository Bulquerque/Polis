"""Unified public surface for Agent 2: P8.S3 and P8.S4."""
from quant_pipeline.phase_08_portfolio_control.scenario_engineering import (
    S3Request, S3Result, run_s3,
)
from quant_pipeline.phase_08_portfolio_control.risk_state import (
    S4Request, S4Result, run_s4,
)

__all__ = ["S3Request", "S3Result", "S4Request", "S4Result", "run_s3", "run_s4"]
__version__ = "0.1.0"
