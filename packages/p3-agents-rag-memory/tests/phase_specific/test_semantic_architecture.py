from pathlib import Path
import yaml


def y(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def modules(root):
    return {d["module_id"]: d for d in (y(p) for p in (root / "modules").glob("*.yaml"))}


def test_person_context_explicitly_contains_stimulus_and_activation(plan_root):
    m = modules(plan_root)["P3.S20.M06"]
    assert {"stimulus_panel", "activation_panel", "retrieved_knowledge_bundle"} <= set(m["inputs"])


def test_memory_retrieval_occurs_after_activation(plan_root):
    m = modules(plan_root)
    assert "activation_panel" in m["P3.S20.M01"]["inputs"]
    assert "person_retrieval_query_panel" in m["P3.S20.M02"]["inputs"]


def test_no_retro_experiment_memory_enters_person_context(plan_root):
    for mid, d in modules(plan_root).items():
        if mid.startswith("P3.S20") or mid.startswith("P3.S21") or mid.startswith("P3.S26"):
            assert "prior_retro_experiment_memory" not in d["inputs"]


def test_actual_tool_execution_chain_exists(plan_root):
    m = modules(plan_root)
    assert m["P3.S21.M02"]["outputs"] == ["validated_tool_call_request_panel"]
    assert "validated_tool_call_request_panel" in m["P3.S21.M03"]["inputs"]
    assert "raw_tool_result_panel" in m["P3.S21.M03"]["outputs"]
    assert "validated_tool_result_panel" in m["P3.S21.M05"]["inputs"]


def test_tool_audit_is_produced_by_executor_not_llm(plan_root):
    m = modules(plan_root)
    assert "tool_call_audit_panel" in m["P3.S21.M03"]["outputs"]
    assert "tool_call_audit_panel" not in m["P3.S21.M01"]["outputs"]


def test_belief_feedback_is_consumed_by_trust_and_memory(plan_root):
    m = modules(plan_root)
    assert "active_belief_feedback_bundle" in m["P3.S25.M01"]["inputs"]
    assert "active_belief_feedback_bundle" in m["P3.S26.M01"]["inputs"]


def test_tag_projection_uses_individual_beliefs_and_weights(plan_root):
    m = modules(plan_root)["P3.S28.M01"]
    assert {"next_belief_state_panel", "validated_population_manifest"} <= set(m["inputs"])


def test_p3_has_no_evaluation_or_promotion_authority_modules(plan_root):
    bad = []
    for mid, d in modules(plan_root).items():
        text = (d["module_name"] + " " + d["function"]).lower()
        if any(x in text for x in ["promotion_gate", "statistical_robustness_evaluation", "retro_feedback_interpreter", "single_change_proposal"]):
            bad.append(mid)
    assert not bad


def test_p9_blueprint_finalizes_experiment_memory(plan_root):
    files = list((plan_root / "cross_phase" / "p9_context_learning" / "modules").glob("*.yaml"))
    names = {y(p)["module_name"] for p in files}
    assert "retro_experiment_record_finalizer" in names


def test_all_config_inputs_have_bindings(plan_root):
    b = y(plan_root / "config" / "CONFIG_BINDINGS.yaml")["bindings"]
    missing = set()
    for d in modules(plan_root).values():
        for i in d["inputs"]:
            if i.endswith("_config") or i in {"p3_schema_authority_inventory", "config_bindings_registry"}:
                if i not in b:
                    missing.add(i)
    assert not missing
    for alias, path in b.items():
        target = (plan_root / "config" / path).resolve()
        assert target.exists(), (alias, path)


def test_every_internal_artifact_has_schema_binding(plan_root):
    arts = {x["artifact"] for x in y(plan_root / "contracts" / "INTERNAL_ARTIFACT_REGISTRY.yaml")}
    bindings = {x["artifact"] for x in y(plan_root / "contracts" / "ARTIFACT_SCHEMA_BINDINGS.yaml")["bindings"]}
    assert arts == bindings


def test_official_output_flags_are_true(plan_root):
    official = set(y(plan_root / "contracts" / "OUTPUT_CONTRACTS.yaml")["official_outputs"])
    reg = {x["artifact"]: x["official_output"] for x in y(plan_root / "contracts" / "INTERNAL_ARTIFACT_REGISTRY.yaml")}
    assert all(reg[x] for x in official)


def test_proposition_and_aggregation_semantics_are_consumed(plan_root):
    m = modules(plan_root)
    assert "proposition_registry_config" in m["P3.S27.M01"]["inputs"]
    assert "aggregation_semantics_config" in m["P3.S27.M01"]["inputs"]
    assert "next_belief_state_panel" in m["P3.S28.M01"]["inputs"]


def test_population_representation_weight_is_required(plan_root):
    s = y(plan_root / "schema_components" / "internal_planned" / "person_profile.yaml")
    assert "representation_weight" in s["required"]


def test_prior_cycle_state_name_is_canonical(plan_root):
    c = y(plan_root / "contracts" / "INPUT_CONTRACTS.yaml")
    assert c["optional_cycle_inputs"] == ["ReplayState"]


def test_no_unresolved_person_context_query_artifact(plan_root):
    for d in modules(plan_root).values():
        assert "person_context_query" not in d["inputs"]


def test_knowledge_cutoff_policy_is_foundation_owned(plan_root):
    assert not (plan_root / "config" / "model_knowledge_cutoff_policy.yaml").exists()
    assert (plan_root / "config" / "governance" / "model_knowledge_cutoff_policy.yaml").exists()


def test_p9_handoff_exists_and_p3_only_exports_evidence(plan_root):
    m = modules(plan_root)
    assert set(m["P3.S31.M01"]["outputs"]) == {"p9_evaluation_evidence_bundle"}
    assert "p9_context_learning_handoff_manifest" in m["P3.S31.M02"]["outputs"]
