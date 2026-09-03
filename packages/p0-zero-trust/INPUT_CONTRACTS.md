# Inputs da Fase 0 — RC4.1

Este documento é uma representação legível de `contracts/INPUT_CONTRACTS.yaml`. A lista abaixo deve permanecer equivalente ao campo `required_inputs`; `optional_feedback_inputs` é vazio nesta fase.

## Inputs obrigatórios

- `agent_phase_package_zip`
- `agent_prompt_templates`
- `agent_skill_definitions_yaml`
- `artifact_format_policy_yaml`
- `artifact_manifest_all_phases`
- `artifact_registry`
- `code_quality_policy_yaml`
- `code_quality_test_report_all_phases`
- `code_standards`
- `connection_matrix_yaml`
- `contract_test_report_all_phases`
- `contracts_all_phases`
- `dashboard_phase_payload_all_phases`
- `file_hash_manifest`
- `fixtures_all_phases`
- `forbidden_connection_matrix_yaml`
- `forbidden_fields_yaml`
- `forbidden_import_policy_yaml`
- `global_architecture_config`
- `global_contracts`
- `hash_history`
- `hash_policy_yaml`
- `manifesto_all_packages`
- `module_io_matrix_all_phases`
- `module_registry_yaml`
- `modules_yaml_all_phases`
- `phase_registry_yaml`
- `release_manifest_previous`
- `schema_test_report_all_phases`
- `schemas_all_phases`
- `source_tree_manifest`
- `subphase_registry_yaml`
- `test_run_report_all_phases`
- `testing_standards`
- `tests_all_phases`
- `zero_trust_rules`

## Inputs opcionais

Nenhum: `optional_feedback_inputs: []`.

## Campos proibidos

- `features`
- `predictions`
- `candidates`
- `rankings`
- `orders`
- `positions`
- `pnl`
- `trade_decisions`

## Pacotes e diretórios lidos

- `contracts/*.yaml`
- `schemas/*.schema.yaml`
- `modules/*.yaml`
- `subphases/*.md`
- `tests/`
- `src/`
- `MANIFESTO.csv`
