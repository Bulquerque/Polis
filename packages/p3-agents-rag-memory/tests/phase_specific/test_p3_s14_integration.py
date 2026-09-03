from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.foundation.memory.service import LocalAtomicJsonlMemoryIndex, MemoryIndexManifestBuilder
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S14_M02_memory_index_manifest_builder import run_module
from .test_p3_s14_m02_memory_index_manifest_builder import _load, _policy


def test_genesis_refresh_reload_sequence(root, tmp_path):
    index = LocalAtomicJsonlMemoryIndex(tmp_path / "memory")
    builder = MemoryIndexManifestBuilder(index)
    base = {"memory_access_policy": _policy(root), "retrieval_config": _load(root, "retrieval_config")}
    genesis = run_module({**base, "current_memory_state": _load(root, "current_memory_state_empty")}, {"memory_index_manifest_builder": builder})["memory_index_manifest"]
    refresh = run_module({**base, "current_memory_state": _load(root, "current_memory_state_populated")}, {"memory_index_manifest_builder": builder})["memory_index_manifest"]
    repeat = run_module({**base, "current_memory_state": _load(root, "current_memory_state_populated")}, {"memory_index_manifest_builder": builder})["memory_index_manifest"]
    assert genesis["status"] == "EMPTY_VALID"
    assert refresh["content_hash"] == repeat["content_hash"]
