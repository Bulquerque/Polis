import asyncio
from quant_pipeline.phase_03_agents_rag_memory.governance.live_safety import EgressPolicy, LiveProbeStatus, qualify_provider_probe

async def _ok(): return {"available_at":"2026-01-01T00:00:00Z","value":1}
async def _slow(): await asyncio.sleep(0.05); return {"available_at":"x"}

def test_live_probe_success_and_timeout():
    policy=EgressPolicy(allowed_hosts=("api.example.com",))
    success=asyncio.run(qualify_provider_probe(provider_id="p",endpoint_url="https://api.example.com",egress_policy=policy,
        probe=_ok,response_validator=lambda x:isinstance(x,dict) and "value" in x,provider_version="1",timeout_seconds=1))
    assert success.status is LiveProbeStatus.PASS
    timeout=asyncio.run(qualify_provider_probe(provider_id="p",endpoint_url="https://api.example.com",egress_policy=policy,
        probe=_slow,response_validator=lambda x:True,provider_version="1",timeout_seconds=0.001))
    assert timeout.status is LiveProbeStatus.TIMEOUT
