from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M02_phase3_run_snapshot_builder import run_module

from .test_p3_s2_temporal_authority import _snapshot


def test_p3_s2_m02_snapshot_is_stable_and_p3_authoritative(root):
    _, snapshot = _snapshot(root)
    assert snapshot["identity"]["architecture_revision"] == "P3-FINAL"
    assert len(snapshot["snapshot_hash"]) == 64
