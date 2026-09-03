from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M01_point_in_time_context_gate import run_module

from .test_p3_s2_temporal_authority import _pit, ArtifactResolver


def test_p3_s2_m01_accepts_only_as_of_context(root):
    payload, pit = _pit(root)
    assert pit["validation_status"] == "READY"
    assert pit["summary"]["accepted"] == 3
    assert ArtifactResolver(payload)
