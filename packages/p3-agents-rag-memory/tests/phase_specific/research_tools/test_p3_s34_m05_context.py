from __future__ import annotations

from copy import deepcopy
import pytest

from .support_s34 import build_s34_m05, s20_context_bundle
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import ValidatedPersonContextBundle


def test_context_projection_matches_exact_s21_contract() -> None:
    out = build_s34_m05()
    bundle = ValidatedPersonContextBundle.model_validate(out["extended_validated_person_context_bundle"], strict=False)
    assert len(bundle.items) == 2
    for item in bundle.items:
        assert item.context_token_count <= item.context_token_limit
        assert item.tool_budget <= 5
        assert "AUTHORIZED_RESEARCH_TOOLS" in item.prompt_context
        assert "trade execution" in item.prompt_context
        assert item.allowed_tool_ids


def test_context_contains_only_authorized_operation_descriptors() -> None:
    out = build_s34_m05()
    audit = out["context_projection_audit"]
    included = [d for d in audit["descriptors"] if d["included"]]
    assert included
    by_person = {r["person_id"]: set(r["allowed_tool_ids"]) for r in audit["records"]}
    assert all(d["tool_id"] in by_person[d["person_id"]] for d in included)


def test_as_of_mismatch_fails_closed() -> None:
    context = deepcopy(s20_context_bundle())
    context["records"][0]["context"]["as_of"] = "2024-01-16T12:00:00Z"
    with pytest.raises(ResearchToolContractError) as exc:
        build_s34_m05({"validated_person_context_bundle": context})
    assert exc.value.reason_code == "P3RT-PIT-3445"


def test_context_projection_is_deterministic() -> None:
    assert build_s34_m05() == build_s34_m05()
