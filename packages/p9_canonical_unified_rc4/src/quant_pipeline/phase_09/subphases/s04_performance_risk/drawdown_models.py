"""Drawdown path contracts for P9.S4.M04."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from .base_models import ModulePanelBase
from .common import FiniteFloat, NonEmptyStr, SemVer, StrictModel, UtcDateTime, content_sha256
from .return_models import WealthPathPanel


class DrawdownPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    conditional_tail_fraction: FiniteFloat = Field(default=0.20, gt=0, le=1)


class UnderwaterPoint(StrictModel):
    timestamp: UtcDateTime
    high_water_mark: FiniteFloat
    wealth: FiniteFloat
    drawdown_fraction: FiniteFloat = Field(le=0)


class DrawdownEpisode(StrictModel):
    episode_id: NonEmptyStr
    peak_time: UtcDateTime
    trough_time: UtcDateTime
    recovery_time: UtcDateTime | None
    maximum_drawdown_fraction: FiniteFloat = Field(le=0)
    duration_seconds: int = Field(ge=0)
    recovery_seconds: int | None = Field(default=None, ge=0)
    censored: bool

    @model_validator(mode="after")
    def validate_episode(self) -> Self:
        if self.trough_time < self.peak_time:
            raise ValueError("trough cannot precede peak")
        if self.censored and self.recovery_time is not None:
            raise ValueError("censored drawdown cannot have recovery_time")
        if not self.censored and self.recovery_time is None:
            raise ValueError("closed drawdown requires recovery_time")
        return self


class DrawdownEpisodePanel(ModulePanelBase):
    episodes: tuple[DrawdownEpisode, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("drawdown episode panel hash mismatch")
        return self


class DrawdownMetricPanel(ModulePanelBase):
    open_episode_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("drawdown metric panel hash mismatch")
        return self


class UnderwaterSeries(ModulePanelBase):
    points: tuple[UnderwaterPoint, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("underwater series hash mismatch")
        return self


class DrawdownRequest(StrictModel):
    wealth_path: WealthPathPanel
    policy: DrawdownPolicy


class DrawdownResult(StrictModel):
    episodes: DrawdownEpisodePanel
    metrics: DrawdownMetricPanel
    underwater: UnderwaterSeries
