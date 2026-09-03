from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .enums import ExecutionMode
from .models import NonEmptyStr, TimeAwareModel


class ModuleExecutionContext(TimeAwareModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: datetime
    market_cutoff_at: datetime
    trace_id: NonEmptyStr
    policy_version: NonEmptyStr
    mode: ExecutionMode = ExecutionMode.BACKTEST
    deterministic_seed: int = Field(default=0, ge=0)
