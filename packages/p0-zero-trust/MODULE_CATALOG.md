# Catálogo de módulos — Fase 0 — RC4.1

Fonte única: `contracts/MODULE_IO_MATRIX.yaml`; detalhes carregados dos 40 contratos YAML correspondentes.

Total: **40 módulos** em **9 subfases**.

## P0.S1.M01 — phase_registry_loader

- Subfase: `P0.S1`
- Contrato: `modules/P0_S1_M01_phase_registry_loader.yaml`
- Função: Executar phase registry loader da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `phase_registry_yaml`, `global_architecture_config`
- Outputs: `validated_phase_registry`
- Validações: `phase_id_unique`, `phase_type_declared`
- Consumidores: `P0.S1.M02`, `P0.S1.M03`, `P0.S1.M04`, `P0.S7.M01`, `P0.S8.M01`

## P0.S1.M02 — subphase_registry_loader

- Subfase: `P0.S1`
- Contrato: `modules/P0_S1_M02_subphase_registry_loader.yaml`
- Função: Executar subphase registry loader da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `validated_phase_registry`, `subphase_registry_yaml`
- Outputs: `validated_subphase_registry`
- Validações: `subphase_id_unique`, `subphase_belongs_to_existing_phase`
- Consumidores: `P0.S1.M03`

## P0.S1.M03 — module_registry_loader

- Subfase: `P0.S1`
- Contrato: `modules/P0_S1_M03_module_registry_loader.yaml`
- Função: Executar module registry loader da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `validated_phase_registry`, `validated_subphase_registry`, `module_registry_yaml`
- Outputs: `validated_module_registry`
- Validações: `module_id_unique`, `module_has_contract`
- Consumidores: `P0.S1.M04`, `P0.S3.M02`, `P0.S4.M02`, `P0.S5.M05`, `P0.S7.M01`

## P0.S1.M04 — connection_matrix_validator

- Subfase: `P0.S1`
- Contrato: `modules/P0_S1_M04_connection_matrix_validator.yaml`
- Função: Executar connection matrix validator da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `connection_matrix_yaml`, `validated_phase_registry`, `validated_module_registry`
- Outputs: `validated_connection_matrix`
- Validações: `economic_connections_allowed_only`, `zero_trust_plane_metadata_only`
- Consumidores: `P0.S1.M05`, `P0.S2.M03`

## P0.S1.M05 — forbidden_connection_detector

- Subfase: `P0.S1`
- Contrato: `modules/P0_S1_M05_forbidden_connection_detector.yaml`
- Função: Executar forbidden connection detector da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `validated_connection_matrix`, `forbidden_connection_matrix_yaml`, `module_io_matrix_all_phases`
- Outputs: `forbidden_connection_report`
- Validações: `no_forbidden_economic_connection`, `phase0_not_economic_input`
- Consumidores: `P0.S6.M03`, `P0.S8.M03`

## P0.S2.M01 — contract_registry_builder

- Subfase: `P0.S2`
- Contrato: `modules/P0_S2_M01_contract_registry_builder.yaml`
- Função: Executar contract registry builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `contracts_all_phases`, `global_contracts`
- Outputs: `contract_registry`
- Validações: `contract_has_source_target`, `shared_artifacts_have_schema`
- Consumidores: `P0.S2.M03`, `P0.S3.M02`, `P0.S4.M02`, `P0.S8.M01`

## P0.S2.M02 — schema_registry_builder

- Subfase: `P0.S2`
- Contrato: `modules/P0_S2_M02_schema_registry_builder.yaml`
- Função: Executar schema registry builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `schemas_all_phases`
- Outputs: `schema_registry`
- Validações: `schema_id_unique`, `required_fields_not_empty`
- Consumidores: `P0.S2.M03`, `P0.S2.M04`, `P0.S4.M02`, `P0.S4.M03`, `P0.S8.M01`

## P0.S2.M03 — input_output_compatibility_checker

- Subfase: `P0.S2`
- Contrato: `modules/P0_S2_M03_input_output_compatibility_checker.yaml`
- Função: Executar input output compatibility checker da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `contract_registry`, `schema_registry`, `validated_connection_matrix`
- Outputs: `io_compatibility_report`, `schema_compatibility_report`
- Validações: `output_covers_required_input`, `optional_feedback_not_blocking`
- Consumidores: `P0.S6.M03`

## P0.S2.M04 — forbidden_field_scanner

- Subfase: `P0.S2`
- Contrato: `modules/P0_S2_M04_forbidden_field_scanner.yaml`
- Função: Executar forbidden field scanner da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `schema_registry`, `artifact_registry`, `forbidden_fields_yaml`
- Outputs: `forbidden_field_report`
- Validações: `target_not_in_inference`, `rank_score_not_before_phase7`
- Consumidores: —

## P0.S2.M05 — artifact_format_policy_validator

- Subfase: `P0.S2`
- Contrato: `modules/P0_S2_M05_artifact_format_policy_validator.yaml`
- Função: Executar artifact format policy validator da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `artifact_registry`, `artifact_format_policy_yaml`
- Outputs: `artifact_format_validation_report`
- Validações: `format_allowed`, `contracts_in_yaml`
- Consumidores: —

## P0.S3.M01 — hash_policy_enforcer

- Subfase: `P0.S3`
- Contrato: `modules/P0_S3_M01_hash_policy_enforcer.yaml`
- Função: Executar hash policy enforcer da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `artifact_manifest_all_phases`, `hash_policy_yaml`
- Outputs: `hash_integrity_report`
- Validações: `every_artifact_has_hash`, `hash_algorithm_allowed`
- Consumidores: `P0.S3.M03`, `P0.S4.M05`, `P0.S6.M02`, `P0.S8.M03`

## P0.S3.M02 — lineage_integrity_checker

- Subfase: `P0.S3`
- Contrato: `modules/P0_S3_M02_lineage_integrity_checker.yaml`
- Função: Executar lineage integrity checker da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `artifact_manifest_all_phases`, `validated_module_registry`, `contract_registry`
- Outputs: `lineage_integrity_report`
- Validações: `lineage_id_present`, `output_points_to_producer`
- Consumidores: `P0.S3.M03`, `P0.S4.M05`

## P0.S3.M03 — artifact_manifest_auditor

- Subfase: `P0.S3`
- Contrato: `modules/P0_S3_M03_artifact_manifest_auditor.yaml`
- Função: Executar artifact manifest auditor da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `manifesto_all_packages`, `artifact_registry`, `hash_integrity_report`, `lineage_integrity_report`
- Outputs: `artifact_manifest_audit_report`, `artifact_integrity_report`
- Validações: `manifest_file_exists`, `critical_file_present`
- Consumidores: `P0.S6.M01`

## P0.S3.M04 — artifact_immutability_checker

- Subfase: `P0.S3`
- Contrato: `modules/P0_S3_M04_artifact_immutability_checker.yaml`
- Função: Executar artifact immutability checker da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `artifact_manifest_all_phases`, `hash_history`, `release_manifest_previous`
- Outputs: `immutability_report`
- Validações: `no_raw_overwrite`, `schema_change_requires_version_bump`
- Consumidores: —

## P0.S4.M01 — test_report_collector

- Subfase: `P0.S4`
- Contrato: `modules/P0_S4_M01_test_report_collector.yaml`
- Função: Executar test report collector da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `test_run_report_all_phases`, `contract_test_report_all_phases`, `schema_test_report_all_phases`, `code_quality_test_report_all_phases`
- Outputs: `collected_test_reports`
- Validações: `every_phase_emits_test_report`, `test_run_id_unique`
- Consumidores: `P0.S4.M04`

## P0.S4.M02 — contract_test_orchestrator

- Subfase: `P0.S4`
- Contrato: `modules/P0_S4_M02_contract_test_orchestrator.yaml`
- Função: Executar contract test orchestrator da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `contract_registry`, `schema_registry`, `validated_module_registry`
- Outputs: `contract_test_execution_plan`, `contract_test_report`
- Validações: `contract_tests_declared`, `forbidden_connections_tested`
- Consumidores: `P0.S4.M04`

## P0.S4.M03 — schema_test_orchestrator

- Subfase: `P0.S4`
- Contrato: `modules/P0_S4_M03_schema_test_orchestrator.yaml`
- Função: Executar schema test orchestrator da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `schema_registry`, `fixtures_all_phases`
- Outputs: `schema_test_report`
- Validações: `valid_fixture_passes`, `invalid_fixture_fails`
- Consumidores: `P0.S4.M04`

## P0.S4.M04 — test_status_aggregator

- Subfase: `P0.S4`
- Contrato: `modules/P0_S4_M04_test_status_aggregator.yaml`
- Função: Executar test status aggregator da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `collected_test_reports`, `contract_test_report`, `schema_test_report`
- Outputs: `global_test_report`, `phase_test_status_panel`
- Validações: `critical_tests_classified`, `phase_status_computed`
- Consumidores: `P0.S4.M05`, `P0.S6.M01`, `P0.S6.M02`, `P0.S8.M03`, `P0.S9.M01`

## P0.S4.M05 — evidence_package_builder

- Subfase: `P0.S4`
- Contrato: `modules/P0_S4_M05_evidence_package_builder.yaml`
- Função: Executar evidence package builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `global_test_report`, `hash_integrity_report`, `lineage_integrity_report`, `code_quality_report`
- Outputs: `zero_trust_evidence_package`
- Validações: `evidence_complete`, `release_evidence_traceable`
- Consumidores: `P0.S6.M03`, `P0.S8.M02`

## P0.S5.M01 — duplicate_file_detector

- Subfase: `P0.S5`
- Contrato: `modules/P0_S5_M01_duplicate_file_detector.yaml`
- Função: Executar duplicate file detector da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `source_tree_manifest`, `file_hash_manifest`
- Outputs: `duplicate_file_report`
- Validações: `duplicate_hashes_detected`, `schemas_duplicate_check`
- Consumidores: `P0.S5.M06`

## P0.S5.M02 — monolith_code_detector

- Subfase: `P0.S5`
- Contrato: `modules/P0_S5_M02_monolith_code_detector.yaml`
- Função: Executar monolith code detector da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `source_tree_manifest`, `code_quality_policy_yaml`
- Outputs: `monolith_report`
- Validações: `file_line_limit_checked`, `function_line_limit_checked`
- Consumidores: `P0.S5.M06`

## P0.S5.M03 — forbidden_import_detector

- Subfase: `P0.S5`
- Contrato: `modules/P0_S5_M03_forbidden_import_detector.yaml`
- Função: Executar forbidden import detector da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `source_tree_manifest`, `forbidden_import_policy_yaml`
- Outputs: `forbidden_import_report`
- Validações: `no_future_phase_import`, `no_dashboard_as_business_logic`
- Consumidores: `P0.S5.M06`

## P0.S5.M04 — hidden_global_state_detector

- Subfase: `P0.S5`
- Contrato: `modules/P0_S5_M04_hidden_global_state_detector.yaml`
- Função: Executar hidden global state detector da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `source_tree_manifest`, `code_quality_policy_yaml`
- Outputs: `hidden_global_state_report`
- Validações: `no_mutable_global_state`, `no_hardcoded_secret_path`
- Consumidores: `P0.S5.M06`

## P0.S5.M05 — module_contract_coverage_checker

- Subfase: `P0.S5`
- Contrato: `modules/P0_S5_M05_module_contract_coverage_checker.yaml`
- Função: Executar module contract coverage checker da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `validated_module_registry`, `modules_yaml_all_phases`, `tests_all_phases`
- Outputs: `module_contract_coverage_report`
- Validações: `every_module_has_yaml`, `every_module_has_expected_test`
- Consumidores: `P0.S5.M06`

## P0.S5.M06 — code_style_quality_reporter

- Subfase: `P0.S5`
- Contrato: `modules/P0_S5_M06_code_style_quality_reporter.yaml`
- Função: Executar code style quality reporter da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `duplicate_file_report`, `monolith_report`, `forbidden_import_report`, `hidden_global_state_report`, `module_contract_coverage_report`
- Outputs: `code_quality_report`
- Validações: `quality_status_computed`, `blocking_quality_issue_marked`
- Consumidores: `P0.S4.M05`, `P0.S6.M02`, `P0.S8.M03`, `P0.S9.M01`

## P0.S6.M01 — phase_dashboard_payload_collector

- Subfase: `P0.S6`
- Contrato: `modules/P0_S6_M01_phase_dashboard_payload_collector.yaml`
- Função: Executar phase dashboard payload collector da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `dashboard_phase_payload_all_phases`, `phase_test_status_panel`, `artifact_manifest_audit_report`
- Outputs: `collected_phase_dashboard_payloads`
- Validações: `every_phase_dashboard_payload_present`, `phase_id_valid`
- Consumidores: `P0.S6.M02`

## P0.S6.M02 — phase_health_panel_builder

- Subfase: `P0.S6`
- Contrato: `modules/P0_S6_M02_phase_health_panel_builder.yaml`
- Função: Executar phase health panel builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `collected_phase_dashboard_payloads`, `global_test_report`, `code_quality_report`, `hash_integrity_report`
- Outputs: `phase_health_panel`
- Validações: `health_status_computed`, `critical_errors_visible`
- Consumidores: `P0.S6.M03`, `P0.S6.M04`, `P0.S9.M01`

## P0.S6.M03 — global_control_tower_builder

- Subfase: `P0.S6`
- Contrato: `modules/P0_S6_M03_global_control_tower_builder.yaml`
- Função: Executar global control tower builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `phase_health_panel`, `forbidden_connection_report`, `io_compatibility_report`, `zero_trust_evidence_package`
- Outputs: `global_control_tower_payload`, `pipeline_health_report`, `zero_trust_health_report`
- Validações: `global_status_computed`, `release_readiness_visible`
- Consumidores: `P0.S6.M04`, `P0.S8.M02`

## P0.S6.M04 — dashboard_exporter

- Subfase: `P0.S6`
- Contrato: `modules/P0_S6_M04_dashboard_exporter.yaml`
- Função: Executar dashboard exporter da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `global_control_tower_payload`, `phase_health_panel`
- Outputs: `dashboard_export_manifest`, `dashboard_static_site`, `dashboard_json_payloads`
- Validações: `dashboard_payload_valid`, `export_manifest_written`
- Consumidores: —

## P0.S7.M01 — agent_skill_registry_builder

- Subfase: `P0.S7`
- Contrato: `modules/P0_S7_M01_agent_skill_registry_builder.yaml`
- Função: Executar agent skill registry builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `agent_skill_definitions_yaml`, `validated_phase_registry`, `validated_module_registry`
- Outputs: `agent_skill_registry`
- Validações: `skill_id_unique`, `skill_scope_declared`
- Consumidores: `P0.S7.M02`

## P0.S7.M02 — agent_prompt_template_validator

- Subfase: `P0.S7`
- Contrato: `modules/P0_S7_M02_agent_prompt_template_validator.yaml`
- Função: Executar agent prompt template validator da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `agent_prompt_templates`, `agent_skill_registry`, `zero_trust_rules`
- Outputs: `validated_agent_prompt_templates`
- Validações: `prompt_does_not_override_global_contract`, `prompt_limits_phase_scope`
- Consumidores: `P0.S7.M03`

## P0.S7.M03 — agent_execution_policy_builder

- Subfase: `P0.S7`
- Contrato: `modules/P0_S7_M03_agent_execution_policy_builder.yaml`
- Função: Executar agent execution policy builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `validated_agent_prompt_templates`, `code_standards`, `testing_standards`
- Outputs: `agent_execution_policy`
- Validações: `definition_of_done_present`, `required_tests_declared`
- Consumidores: `P0.S7.M04`

## P0.S7.M04 — agent_package_validator

- Subfase: `P0.S7`
- Contrato: `modules/P0_S7_M04_agent_package_validator.yaml`
- Função: Executar agent package validator da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `agent_execution_policy`, `agent_phase_package_zip`
- Outputs: `agent_package_validation_report`
- Validações: `package_structure_valid`, `no_cache_in_zip`
- Consumidores: —

## P0.S8.M01 — version_compatibility_checker

- Subfase: `P0.S8`
- Contrato: `modules/P0_S8_M01_version_compatibility_checker.yaml`
- Função: Executar version compatibility checker da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `validated_phase_registry`, `contract_registry`, `schema_registry`, `release_manifest_previous`
- Outputs: `version_compatibility_report`
- Validações: `schema_version_compatible`, `pipeline_version_consistent`
- Consumidores: `P0.S8.M02`

## P0.S8.M02 — release_manifest_builder

- Subfase: `P0.S8`
- Contrato: `modules/P0_S8_M02_release_manifest_builder.yaml`
- Função: Executar release manifest builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `pipeline_health_report`, `version_compatibility_report`, `zero_trust_evidence_package`
- Outputs: `release_manifest`
- Validações: `release_manifest_traceable`, `release_artifacts_listed`
- Consumidores: `P0.S8.M03`

## P0.S8.M03 — release_gate_decision_engine

- Subfase: `P0.S8`
- Contrato: `modules/P0_S8_M03_release_gate_decision_engine.yaml`
- Função: Executar release gate decision engine da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `release_manifest`, `global_test_report`, `forbidden_connection_report`, `code_quality_report`, `hash_integrity_report`
- Outputs: `release_gate_report`
- Validações: `fail_on_forbidden_connection`, `fail_on_critical_test_failure`
- Consumidores: `P0.S9.M01`

## P0.S9.M01 — phase_feedback_router

- Subfase: `P0.S9`
- Contrato: `modules/P0_S9_M01_phase_feedback_router.yaml`
- Função: Executar phase feedback router da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `release_gate_report`, `phase_health_panel`, `code_quality_report`, `global_test_report`
- Outputs: `phase_zero_trust_feedback_panel`
- Validações: `feedback_per_phase`, `blocking_vs_warning_separated`
- Consumidores: `P0.S9.M02`, `P0.S9.M03`, `P0.S9.M04`

## P0.S9.M02 — blocking_issue_dispatcher

- Subfase: `P0.S9`
- Contrato: `modules/P0_S9_M02_blocking_issue_dispatcher.yaml`
- Função: Executar blocking issue dispatcher da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `phase_zero_trust_feedback_panel`
- Outputs: `blocking_issue_report`
- Validações: `blocking_errors_have_owner`, `blocking_errors_have_action`
- Consumidores: `P0.S9.M04`

## P0.S9.M03 — nonblocking_warning_dispatcher

- Subfase: `P0.S9`
- Contrato: `modules/P0_S9_M03_nonblocking_warning_dispatcher.yaml`
- Função: Executar nonblocking warning dispatcher da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `phase_zero_trust_feedback_panel`
- Outputs: `nonblocking_warning_report`
- Validações: `warnings_have_owner`, `warnings_not_release_blocking`
- Consumidores: `P0.S9.M04`

## P0.S9.M04 — zero_trust_feedback_manifest_builder

- Subfase: `P0.S9`
- Contrato: `modules/P0_S9_M04_zero_trust_feedback_manifest_builder.yaml`
- Função: Executar zero trust feedback manifest builder da Fase 0, mantendo controle Zero Trust técnico e sem tocar no fluxo econômico.
- Inputs: `blocking_issue_report`, `nonblocking_warning_report`, `phase_zero_trust_feedback_panel`
- Outputs: `zero_trust_feedback_manifest`
- Validações: `feedback_manifest_complete`, `phase_feedback_traceable`
- Consumidores: —
