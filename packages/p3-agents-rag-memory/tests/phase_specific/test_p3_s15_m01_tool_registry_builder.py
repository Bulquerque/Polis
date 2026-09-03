import pytest
from .resource_support import build_s15_outputs

@pytest.mark.asyncio
async def test_tool_registry_uses_declared_provider_config(root):
    registry, _, _, sink = await build_s15_outputs(root)
    assert registry["status"] in {"READY", "DEGRADED"}
    assert registry["tools"]
    assert all(item["provider_fingerprint"] for item in registry["tools"])
    assert any(event == "module_succeeded" for event, _ in sink.events)
