from copy import deepcopy

from quant_pipeline.phase_06_strategy_synthesis.foundation.hashing import (
    canonical_sha256,
)
from quant_pipeline.phase_06_strategy_synthesis.orchestration.phase_runner import (
    run_phase,
)


def test_wave1_end_to_end_outputs(inputs, configuration):
    result = run_phase(inputs, configuration)
    required = {
        "strategy_candidate_panel",
        "strategy_leg_panel",
        "strategy_market_snapshot",
        "strategy_payoff_panel",
        "strategy_scenario_evaluation_panel",
        "strategy_greek_panel",
        "strategy_risk_panel",
        "strategy_cost_liquidity_panel",
        "strategy_lineage_panel",
        "strategy_generation_trace_panel",
        "candidate_equivalence_panel",
        "quality_diversity_archive",
        "candidate_rejection_report",
        "candidate_generation_audit",
        "phase7_strategy_handoff_manifest",
    }
    assert required <= result["canonical_outputs"].keys()
    assert result["production_promotion_allowed"] is False
    assert result["subphases"]["P6.S4"].capability_status == "UNAVAILABLE"
    assert result["subphases"]["P6.S5"].capability_status == "UNAVAILABLE"
    assert result["subphases"]["P6.S6"].capability_status == "UNAVAILABLE"


def test_deterministic_replay(inputs, configuration):
    first = run_phase(deepcopy(inputs), deepcopy(configuration))
    second = run_phase(deepcopy(inputs), deepcopy(configuration))
    first_manifest = first["canonical_outputs"]["phase7_strategy_handoff_manifest"]
    second_manifest = second["canonical_outputs"]["phase7_strategy_handoff_manifest"]
    assert first_manifest.content_sha256 == second_manifest.content_sha256
    assert (
        first["canonical_outputs"]["strategy_candidate_panel"].content_sha256
        == second["canonical_outputs"]["strategy_candidate_panel"].content_sha256
    )


def test_input_order_does_not_change_candidates(inputs, configuration):
    first = run_phase(deepcopy(inputs), deepcopy(configuration))
    reordered = deepcopy(inputs)
    for name in ("clean_option_contract_panel", "clean_option_quotes_panel"):
        reordered[name]["records"].reverse()
        reordered[name]["content_sha256"] = canonical_sha256(
            reordered[name]["records"]
        )
    second = run_phase(reordered, deepcopy(configuration))
    first_ids = sorted(
        row.candidate_id
        for row in first["canonical_outputs"]["strategy_candidate_panel"].records
    )
    second_ids = sorted(
        row.candidate_id
        for row in second["canonical_outputs"]["strategy_candidate_panel"].records
    )
    assert first_ids == second_ids


def test_p7_v1_projection_is_explicitly_degraded(inputs, configuration):
    result = run_phase(inputs, configuration)
    artifact = result["phase7_outputs"]["candidate_feature_base_panel"]
    assert artifact.metadata["projection"] == "P7_V1_LIMITED"
    assert artifact.record_count == result["canonical_outputs"][
        "strategy_candidate_panel"
    ].record_count


def test_manifest_reconciles_candidate_count(inputs, configuration):
    result = run_phase(inputs, configuration)
    manifest = result["canonical_outputs"][
        "phase7_strategy_handoff_manifest"
    ].records[0]
    candidates = result["canonical_outputs"]["strategy_candidate_panel"].records
    assert manifest.candidate_count == len(candidates)
    assert manifest.candidate_ids_sha256 == canonical_sha256(
        tuple(sorted(item.candidate_id for item in candidates))
    )


def test_quality_diversity_never_merges_different_underlyings(
    inputs,
    configuration,
):
    expanded = _add_second_underlying(inputs, "ABC")
    result = run_phase(expanded, configuration)
    candidates = result["canonical_outputs"]["strategy_candidate_panel"].records
    niches = result["canonical_outputs"]["quality_diversity_archive"].records

    assert {candidate.underlying_id for candidate in candidates} == {"XYZ", "ABC"}
    assert all(niche.niche_id.startswith(("XYZ|", "ABC|")) for niche in niches)
    assert any(niche.niche_id.startswith("XYZ|") for niche in niches)
    assert any(niche.niche_id.startswith("ABC|") for niche in niches)


def _add_second_underlying(inputs: dict, underlying_id: str) -> dict:
    expanded = deepcopy(inputs)
    for artifact_name in (
        "market_belief_state",
        "clean_option_contract_panel",
        "clean_option_quotes_panel",
        "clean_underlying_trade_panel",
    ):
        copied = [
            _replace_underlying(record, underlying_id)
            for record in inputs[artifact_name]["records"]
        ]
        expanded[artifact_name]["records"].extend(copied)
        expanded[artifact_name]["content_sha256"] = canonical_sha256(
            expanded[artifact_name]["records"]
        )
    return expanded


def _replace_underlying(record: dict, underlying_id: str) -> dict:
    updated = deepcopy(record)
    old_contract_id = updated.get("contract_id")
    if old_contract_id is not None:
        new_contract_id = old_contract_id.replace("XYZ", underlying_id)
        updated["contract_id"] = new_contract_id
        if "source_record_id" in updated:
            updated["source_record_id"] = new_contract_id
        if "source_id" in updated:
            updated["source_id"] = f"quote-{new_contract_id}"
    for field_name in ("underlying", "underlying_id"):
        if field_name in updated:
            updated[field_name] = underlying_id
    if "belief_state_id" in updated:
        updated["belief_state_id"] = f"belief-{underlying_id}"
    if "source_record_id" in updated and old_contract_id is None:
        updated["source_record_id"] = underlying_id
    return updated


def test_cli_json_projection_excludes_internal_runtime_objects(
    inputs,
    configuration,
):
    import json

    from quant_pipeline.phase_06_strategy_synthesis.cli import _jsonable

    payload = _jsonable(run_phase(inputs, configuration))
    encoded = json.dumps(payload, sort_keys=True)
    assert '"_template_plan"' not in encoded
    assert payload["target_release"] == "P6-RC6.2-P5-V2-CLOSURE-RC4"
