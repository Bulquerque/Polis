from __future__ import annotations

import json
import yaml

from quant_pipeline.phase_03_agents_rag_memory.integration.p2_boundary import P2P3BoundaryAdapter


def test_p2_p3_boundary_adapter_uses_canonical_runtime_facade(root):
    payload = json.loads(
        (root / "fixtures/external_compat/p2_real_packager_fixture.json").read_text(encoding="utf-8")
    )
    policy = yaml.safe_load(
        (root / "config/governance/SOURCE_QUALITY_POLICY.yaml").read_text(encoding="utf-8")
    )
    import asyncio

    result = asyncio.run(P2P3BoundaryAdapter().validate(payload, source_quality_policy=policy))
    assert result["boundary"] == "P2.S6.M02->P3.S1.M01->P3.S1.M02"
    assert result["validated_context_inputs"]["summary"]["rejected"] == 0
    assert len(result["p2_input_hash"]) == 64
