"""Named configuration profiles for P2 execution.

Profiles are additive conveniences. They do not change the public module or
phase interfaces. Production-like runs should explicitly opt into strict mode;
legacy/drop-in compatibility remains the default for existing callers.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

STRICT_PRODUCTION_PROFILE: dict[str, Any] = {
    "profile_id": "DAILY_MARK_RESEARCH_BR_V1",
    "required_markets": ["BR"],
    "required_venues": ["B3"],
    "required_capabilities": ["underlying_history", "option_mark_history", "instrument_reference", "market_calendar"],
    "strict_physical_validation": True,
    "strict_temporal_validation": True,
    "strict_source_quality": True,
    "fail_on_blocked_critical_source": True,
    "strict_schema_validation": True,
    "strict_target_readiness": True,
    "allow_degraded_handoffs": False,
    "allow_legacy_unverified": False,
}

DAILY_MARK_RESEARCH_BR_V1 = deepcopy(STRICT_PRODUCTION_PROFILE)

DAILY_MARK_RESEARCH_US_V1: dict[str, Any] = {
    **STRICT_PRODUCTION_PROFILE,
    "profile_id": "DAILY_MARK_RESEARCH_US_V1",
    "required_markets": ["US"],
    "required_venues": ["OPRA", "NASDAQ"],
    "required_capabilities": ["underlying_history", "option_contract_reference", "option_mark_or_trade_history"],
    "provider_id": "LONDON_STRATEGIC_EDGE",
    "required_for_core_closure": False,
}

MULTI_MARKET_BR_US_V1: dict[str, Any] = {
    **STRICT_PRODUCTION_PROFILE,
    "profile_id": "MULTI_MARKET_BR_US_V1",
    "includes": ["DAILY_MARK_RESEARCH_BR_V1", "DAILY_MARK_RESEARCH_US_V1"],
    "required_markets": ["BR", "US"],
    "required_for_core_closure": False,
}

CANONICAL_OPTIONS_PROFILE: dict[str, Any] = {
    **STRICT_PRODUCTION_PROFILE,
    "allowed_option_providers": ["LONDON_STRATEGIC_EDGE", "B3_PUBLIC_DATA", "B3_COTAHIST"],
    "source_priority": ["LONDON_STRATEGIC_EDGE", "B3_PUBLIC_DATA", "B3_COTAHIST"],
    "option_source_policy": "LSE_PRIMARY_B3_PRIMARY_SECONDARIES_OPTIONAL",
}

LSE_ONLY_PROFILE: dict[str, Any] = deepcopy(CANONICAL_OPTIONS_PROFILE)


def strict_production_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = deepcopy(STRICT_PRODUCTION_PROFILE)
    if overrides:
        config.update(overrides)
    return config


def lse_only_production_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    # Kept as a compatibility name; the active policy is now LSE + B3.
    config = deepcopy(CANONICAL_OPTIONS_PROFILE)
    if overrides:
        config.update(overrides)
    return config
