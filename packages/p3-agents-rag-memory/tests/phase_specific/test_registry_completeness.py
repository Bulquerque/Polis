import yaml


def y(p): return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_schema_registry_covers_all_schema_files(plan_root):
    doc=y(plan_root/"schemas"/"SCHEMA_REGISTRY.yaml")
    reg={x["schema"] for x in doc["schemas"]}
    canonical={p.name for p in (plan_root/"schemas").glob("*.schema.yaml")}
    all_files={p.relative_to(plan_root/"schemas").as_posix() for p in (plan_root/"schemas").rglob("*") if p.is_file() and p.name != "SCHEMA_REGISTRY.yaml" and p.suffix in {".yaml",".yml",".json"}}
    assert doc["schema_count"]==len(all_files)
    assert reg==all_files

def test_every_artifact_schema_binding_path_exists(plan_root):
    for row in y(plan_root/"contracts"/"ARTIFACT_SCHEMA_BINDINGS.yaml")["bindings"]:
        assert (plan_root/row["schema"]).exists(), row


def test_p9_only_configs_are_not_in_p3_config_surface(plan_root):
    forbidden={"reward_vector_config.yaml","statistical_robustness_config.yaml","research_budget_policy.yaml","mutation_taxonomy.yaml","ablation_config.yaml","data_vault_policy.yaml"}
    assert not (forbidden & {p.name for p in (plan_root/"config").glob("*.yaml")})
    assert forbidden <= {p.name for p in (plan_root/"cross_phase"/"p9_context_learning"/"config").glob("*.yaml")}
