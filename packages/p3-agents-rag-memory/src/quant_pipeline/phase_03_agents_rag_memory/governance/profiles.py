"""Fail-closed provider qualification gates shared by RAG, tools and cognition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from ..contracts import ContractModel, ExecutionProfile


class ProviderQualification(ContractModel):
    provider_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    status: str = Field(pattern=r"^(QUALIFIED|DEGRADED|DISABLED|UNVERIFIED)$")
    persistent: bool = False
    versioned: bool = False
    health_checked: bool = False


def require_qualified_capability(
    profile: ExecutionProfile,
    capability: str,
    provider: ProviderQualification | Mapping[str, Any] | None,
) -> ProviderQualification | None:
    """Reject reference or unqualified providers outside TEST."""

    if provider is None:
        if profile is ExecutionProfile.TEST:
            return None
        raise RuntimeError(f"{capability} provider is required in {profile.value}")
    value = provider if isinstance(provider, ProviderQualification) else ProviderQualification.model_validate(provider)
    if profile is ExecutionProfile.TEST:
        return value
    if value.status != "QUALIFIED":
        raise RuntimeError(f"{capability} provider {value.provider_id} is not QUALIFIED")
    if not value.versioned:
        raise RuntimeError(f"{capability} provider {value.provider_id} is not versioned")
    if profile is ExecutionProfile.LIVE and (not value.persistent or not value.health_checked):
        raise RuntimeError(f"{capability} provider {value.provider_id} is not LIVE-ready")
    return value
