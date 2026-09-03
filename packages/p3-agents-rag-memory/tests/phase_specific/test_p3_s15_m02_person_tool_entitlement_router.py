import pytest
from .resource_support import build_s15_outputs

@pytest.mark.asyncio
async def test_entitlements_are_deny_by_default_and_role_scoped(root):
    _, entitlements, _, _ = await build_s15_outputs(root)
    records = entitlements["records"]
    assert records
    allowed = [item for item in records if item["decision"] == "ALLOWED"]
    denied = [item for item in records if item["decision"] == "DENIED"]
    assert allowed
    assert denied
    assert all(item["person_id"] == "person-quant-1" for item in records)
