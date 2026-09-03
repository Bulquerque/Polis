from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyAdapterPolicy:
    allow_temporal_fallback: bool = False
    allow_generated_lineage: bool = False
    allow_naive_datetime_utc: bool = False
