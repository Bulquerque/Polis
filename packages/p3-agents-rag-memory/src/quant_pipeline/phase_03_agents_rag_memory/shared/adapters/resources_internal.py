from __future__ import annotations

from pydantic import ValidationError

from ...foundation.resources.gateway import models as s16
from ...foundation.resources.tool_registry import models as s15


class ResourceBoundaryError(ValueError):
    """Raised when an S15 artifact cannot cross the canonical S15→S16 boundary."""


def _convert(value: object, target: type, boundary: str):
    try:
        payload = value.model_dump(mode="json")  # type: ignore[attr-defined]
        return target.model_validate(payload, strict=False)
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise ResourceBoundaryError(f"{boundary}: {exc}") from exc


def tool_registry_to_gateway(value: s15.ToolRegistryArtifact) -> s16.ToolRegistryArtifact:
    """Project the S15 authority into S16 without changing identity or content hash."""
    result = _convert(value, s16.ToolRegistryArtifact, "P3.S15→P3.S16 tool_registry")
    if result.content_hash != value.content_hash or result.artifact_id != value.artifact_id:
        raise ResourceBoundaryError("tool registry identity changed during boundary projection")
    return result


def entitlements_to_gateway(value: s15.PersonToolEntitlementPanel) -> s16.PersonToolEntitlementPanel:
    """Project S15 entitlements into the S16 validation surface."""
    result = _convert(value, s16.PersonToolEntitlementPanel, "P3.S15→P3.S16 entitlement_panel")
    if result.content_hash != value.content_hash or result.tool_registry_hash != value.tool_registry_hash:
        raise ResourceBoundaryError("entitlement identity or linkage changed during boundary projection")
    return result


def provider_registry_to_gateway(value: s15.ProviderAdapterRegistry) -> s16.ProviderAdapterRegistry:
    """Project the S15 provider registry into the gateway's narrower read-only view."""
    return _convert(value, s16.ProviderAdapterRegistry, "P3.S15→P3.S16 provider_registry")
