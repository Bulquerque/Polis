from __future__ import annotations

import pytest
from .resource_support import build_s15_outputs


@pytest.mark.asyncio
async def test_registry_to_entitlement_pipeline_is_deny_by_default(root):
    registry, entitlements, providers, sink = await build_s15_outputs(root)
    assert registry["tools"]
    assert entitlements["records"]
    assert {item["provider_id"] for item in registry["tools"]} <= {item.provider_id for item in providers.adapters}
    decisions = {item["decision"] for item in entitlements["records"]}
    assert "ALLOWED" in decisions
    assert "DENIED" in decisions
    assert all(item["allowed_operations"] for item in entitlements["records"] if item["decision"] == "ALLOWED")
    assert all(not item["allowed_operations"] for item in entitlements["records"] if item["decision"] == "DENIED")
    assert sink.events
