from __future__ import annotations

import json
import pytest

from quant_pipeline.phase_03_agents_rag_memory.foundation.memory.errors import MemoryPolicyError
from quant_pipeline.phase_03_agents_rag_memory.foundation.memory.service import MemoryPolicyBuilder
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S14_M01_memory_access_policy_builder import run_module


def _load(root, name):
    return json.loads((root / f"fixtures/warmup_memory/s14/valid/{name}.json").read_text())


def test_memory_policy_is_deny_by_default_for_audit_scope(root):
    output = run_module({
        "memory_access_config": _load(root, "memory_access_config"),
        "person_schema_policy": _load(root, "person_schema_policy"),
        "phase3_run_snapshot": _load(root, "phase3_run_snapshot"),
    }, {"memory_policy_builder": MemoryPolicyBuilder()})["memory_access_policy"]
    scopes = {item["visibility_scope"]: item for item in output["scope_policies"]}
    assert output["audit_memory_separate"] is True
    assert scopes["AUDIT_ONLY"]["retrievable"] is False


def test_memory_policy_rejects_incompatible_person_ontology(root):
    policy = _load(root, "person_schema_policy")
    policy["allowed_memory_types"] = policy["allowed_memory_types"][:-1]
    with pytest.raises(MemoryPolicyError):
        run_module({
            "memory_access_config": _load(root, "memory_access_config"),
            "person_schema_policy": policy,
            "phase3_run_snapshot": _load(root, "phase3_run_snapshot"),
        }, {"memory_policy_builder": MemoryPolicyBuilder()})
