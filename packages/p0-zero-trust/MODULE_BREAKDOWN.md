# Breakdown operacional dos módulos — Fase 0 — RC4.1

Este documento é gerado da matriz canônica e não é uma fonte alternativa de contratos.

## P0.S1.M01 — phase_registry_loader

**Subfase.** `P0.S1`
**Recebe.** `phase_registry_yaml`, `global_architecture_config`
**Produz.** `validated_phase_registry`
**Validações.** `phase_id_unique`, `phase_type_declared`
**Falha rápida.** `phase_registry_loader_critical_failure`

## P0.S1.M02 — subphase_registry_loader

**Subfase.** `P0.S1`
**Recebe.** `validated_phase_registry`, `subphase_registry_yaml`
**Produz.** `validated_subphase_registry`
**Validações.** `subphase_id_unique`, `subphase_belongs_to_existing_phase`
**Falha rápida.** `subphase_registry_loader_critical_failure`

## P0.S1.M03 — module_registry_loader

**Subfase.** `P0.S1`
**Recebe.** `validated_phase_registry`, `validated_subphase_registry`, `module_registry_yaml`
**Produz.** `validated_module_registry`
**Validações.** `module_id_unique`, `module_has_contract`
**Falha rápida.** `module_registry_loader_critical_failure`

## P0.S1.M04 — connection_matrix_validator

**Subfase.** `P0.S1`
**Recebe.** `connection_matrix_yaml`, `validated_phase_registry`, `validated_module_registry`
**Produz.** `validated_connection_matrix`
**Validações.** `economic_connections_allowed_only`, `zero_trust_plane_metadata_only`
**Falha rápida.** `connection_matrix_validator_critical_failure`

## P0.S1.M05 — forbidden_connection_detector

**Subfase.** `P0.S1`
**Recebe.** `validated_connection_matrix`, `forbidden_connection_matrix_yaml`, `module_io_matrix_all_phases`
**Produz.** `forbidden_connection_report`
**Validações.** `no_forbidden_economic_connection`, `phase0_not_economic_input`
**Falha rápida.** `forbidden_connection_detector_critical_failure`

## P0.S2.M01 — contract_registry_builder

**Subfase.** `P0.S2`
**Recebe.** `contracts_all_phases`, `global_contracts`
**Produz.** `contract_registry`
**Validações.** `contract_has_source_target`, `shared_artifacts_have_schema`
**Falha rápida.** `contract_registry_builder_critical_failure`

## P0.S2.M02 — schema_registry_builder

**Subfase.** `P0.S2`
**Recebe.** `schemas_all_phases`
**Produz.** `schema_registry`
**Validações.** `schema_id_unique`, `required_fields_not_empty`
**Falha rápida.** `schema_registry_builder_critical_failure`

## P0.S2.M03 — input_output_compatibility_checker

**Subfase.** `P0.S2`
**Recebe.** `contract_registry`, `schema_registry`, `validated_connection_matrix`
**Produz.** `io_compatibility_report`, `schema_compatibility_report`
**Validações.** `output_covers_required_input`, `optional_feedback_not_blocking`
**Falha rápida.** `input_output_compatibility_checker_critical_failure`

## P0.S2.M04 — forbidden_field_scanner

**Subfase.** `P0.S2`
**Recebe.** `schema_registry`, `artifact_registry`, `forbidden_fields_yaml`
**Produz.** `forbidden_field_report`
**Validações.** `target_not_in_inference`, `rank_score_not_before_phase7`
**Falha rápida.** `forbidden_field_scanner_critical_failure`

## P0.S2.M05 — artifact_format_policy_validator

**Subfase.** `P0.S2`
**Recebe.** `artifact_registry`, `artifact_format_policy_yaml`
**Produz.** `artifact_format_validation_report`
**Validações.** `format_allowed`, `contracts_in_yaml`
**Falha rápida.** `artifact_format_policy_validator_critical_failure`

## P0.S3.M01 — hash_policy_enforcer

**Subfase.** `P0.S3`
**Recebe.** `artifact_manifest_all_phases`, `hash_policy_yaml`
**Produz.** `hash_integrity_report`
**Validações.** `every_artifact_has_hash`, `hash_algorithm_allowed`
**Falha rápida.** `hash_policy_enforcer_critical_failure`

## P0.S3.M02 — lineage_integrity_checker

**Subfase.** `P0.S3`
**Recebe.** `artifact_manifest_all_phases`, `validated_module_registry`, `contract_registry`
**Produz.** `lineage_integrity_report`
**Validações.** `lineage_id_present`, `output_points_to_producer`
**Falha rápida.** `lineage_integrity_checker_critical_failure`

## P0.S3.M03 — artifact_manifest_auditor

**Subfase.** `P0.S3`
**Recebe.** `manifesto_all_packages`, `artifact_registry`, `hash_integrity_report`, `lineage_integrity_report`
**Produz.** `artifact_manifest_audit_report`, `artifact_integrity_report`
**Validações.** `manifest_file_exists`, `critical_file_present`
**Falha rápida.** `artifact_manifest_auditor_critical_failure`

## P0.S3.M04 — artifact_immutability_checker

**Subfase.** `P0.S3`
**Recebe.** `artifact_manifest_all_phases`, `hash_history`, `release_manifest_previous`
**Produz.** `immutability_report`
**Validações.** `no_raw_overwrite`, `schema_change_requires_version_bump`
**Falha rápida.** `artifact_immutability_checker_critical_failure`

## P0.S4.M01 — test_report_collector

**Subfase.** `P0.S4`
**Recebe.** `test_run_report_all_phases`, `contract_test_report_all_phases`, `schema_test_report_all_phases`, `code_quality_test_report_all_phases`
**Produz.** `collected_test_reports`
**Validações.** `every_phase_emits_test_report`, `test_run_id_unique`
**Falha rápida.** `test_report_collector_critical_failure`

## P0.S4.M02 — contract_test_orchestrator

**Subfase.** `P0.S4`
**Recebe.** `contract_registry`, `schema_registry`, `validated_module_registry`
**Produz.** `contract_test_execution_plan`, `contract_test_report`
**Validações.** `contract_tests_declared`, `forbidden_connections_tested`
**Falha rápida.** `contract_test_orchestrator_critical_failure`

## P0.S4.M03 — schema_test_orchestrator

**Subfase.** `P0.S4`
**Recebe.** `schema_registry`, `fixtures_all_phases`
**Produz.** `schema_test_report`
**Validações.** `valid_fixture_passes`, `invalid_fixture_fails`
**Falha rápida.** `schema_test_orchestrator_critical_failure`

## P0.S4.M04 — test_status_aggregator

**Subfase.** `P0.S4`
**Recebe.** `collected_test_reports`, `contract_test_report`, `schema_test_report`
**Produz.** `global_test_report`, `phase_test_status_panel`
**Validações.** `critical_tests_classified`, `phase_status_computed`
**Falha rápida.** `test_status_aggregator_critical_failure`

## P0.S4.M05 — evidence_package_builder

**Subfase.** `P0.S4`
**Recebe.** `global_test_report`, `hash_integrity_report`, `lineage_integrity_report`, `code_quality_report`
**Produz.** `zero_trust_evidence_package`
**Validações.** `evidence_complete`, `release_evidence_traceable`
**Falha rápida.** `evidence_package_builder_critical_failure`

## P0.S5.M01 — duplicate_file_detector

**Subfase.** `P0.S5`
**Recebe.** `source_tree_manifest`, `file_hash_manifest`
**Produz.** `duplicate_file_report`
**Validações.** `duplicate_hashes_detected`, `schemas_duplicate_check`
**Falha rápida.** `duplicate_file_detector_critical_failure`

## P0.S5.M02 — monolith_code_detector

**Subfase.** `P0.S5`
**Recebe.** `source_tree_manifest`, `code_quality_policy_yaml`
**Produz.** `monolith_report`
**Validações.** `file_line_limit_checked`, `function_line_limit_checked`
**Falha rápida.** `monolith_code_detector_critical_failure`

## P0.S5.M03 — forbidden_import_detector

**Subfase.** `P0.S5`
**Recebe.** `source_tree_manifest`, `forbidden_import_policy_yaml`
**Produz.** `forbidden_import_report`
**Validações.** `no_future_phase_import`, `no_dashboard_as_business_logic`
**Falha rápida.** `forbidden_import_detector_critical_failure`

## P0.S5.M04 — hidden_global_state_detector

**Subfase.** `P0.S5`
**Recebe.** `source_tree_manifest`, `code_quality_policy_yaml`
**Produz.** `hidden_global_state_report`
**Validações.** `no_mutable_global_state`, `no_hardcoded_secret_path`
**Falha rápida.** `hidden_global_state_detector_critical_failure`

## P0.S5.M05 — module_contract_coverage_checker

**Subfase.** `P0.S5`
**Recebe.** `validated_module_registry`, `modules_yaml_all_phases`, `tests_all_phases`
**Produz.** `module_contract_coverage_report`
**Validações.** `every_module_has_yaml`, `every_module_has_expected_test`
**Falha rápida.** `module_contract_coverage_checker_critical_failure`

## P0.S5.M06 — code_style_quality_reporter

**Subfase.** `P0.S5`
**Recebe.** `duplicate_file_report`, `monolith_report`, `forbidden_import_report`, `hidden_global_state_report`, `module_contract_coverage_report`
**Produz.** `code_quality_report`
**Validações.** `quality_status_computed`, `blocking_quality_issue_marked`
**Falha rápida.** `code_style_quality_reporter_critical_failure`

## P0.S6.M01 — phase_dashboard_payload_collector

**Subfase.** `P0.S6`
**Recebe.** `dashboard_phase_payload_all_phases`, `phase_test_status_panel`, `artifact_manifest_audit_report`
**Produz.** `collected_phase_dashboard_payloads`
**Validações.** `every_phase_dashboard_payload_present`, `phase_id_valid`
**Falha rápida.** `phase_dashboard_payload_collector_critical_failure`

## P0.S6.M02 — phase_health_panel_builder

**Subfase.** `P0.S6`
**Recebe.** `collected_phase_dashboard_payloads`, `global_test_report`, `code_quality_report`, `hash_integrity_report`
**Produz.** `phase_health_panel`
**Validações.** `health_status_computed`, `critical_errors_visible`
**Falha rápida.** `phase_health_panel_builder_critical_failure`

## P0.S6.M03 — global_control_tower_builder

**Subfase.** `P0.S6`
**Recebe.** `phase_health_panel`, `forbidden_connection_report`, `io_compatibility_report`, `zero_trust_evidence_package`
**Produz.** `global_control_tower_payload`, `pipeline_health_report`, `zero_trust_health_report`
**Validações.** `global_status_computed`, `release_readiness_visible`
**Falha rápida.** `global_control_tower_builder_critical_failure`

## P0.S6.M04 — dashboard_exporter

**Subfase.** `P0.S6`
**Recebe.** `global_control_tower_payload`, `phase_health_panel`
**Produz.** `dashboard_export_manifest`, `dashboard_static_site`, `dashboard_json_payloads`
**Validações.** `dashboard_payload_valid`, `export_manifest_written`
**Falha rápida.** `dashboard_exporter_critical_failure`

## P0.S7.M01 — agent_skill_registry_builder

**Subfase.** `P0.S7`
**Recebe.** `agent_skill_definitions_yaml`, `validated_phase_registry`, `validated_module_registry`
**Produz.** `agent_skill_registry`
**Validações.** `skill_id_unique`, `skill_scope_declared`
**Falha rápida.** `agent_skill_registry_builder_critical_failure`

## P0.S7.M02 — agent_prompt_template_validator

**Subfase.** `P0.S7`
**Recebe.** `agent_prompt_templates`, `agent_skill_registry`, `zero_trust_rules`
**Produz.** `validated_agent_prompt_templates`
**Validações.** `prompt_does_not_override_global_contract`, `prompt_limits_phase_scope`
**Falha rápida.** `agent_prompt_template_validator_critical_failure`

## P0.S7.M03 — agent_execution_policy_builder

**Subfase.** `P0.S7`
**Recebe.** `validated_agent_prompt_templates`, `code_standards`, `testing_standards`
**Produz.** `agent_execution_policy`
**Validações.** `definition_of_done_present`, `required_tests_declared`
**Falha rápida.** `agent_execution_policy_builder_critical_failure`

## P0.S7.M04 — agent_package_validator

**Subfase.** `P0.S7`
**Recebe.** `agent_execution_policy`, `agent_phase_package_zip`
**Produz.** `agent_package_validation_report`
**Validações.** `package_structure_valid`, `no_cache_in_zip`
**Falha rápida.** `agent_package_validator_critical_failure`

## P0.S8.M01 — version_compatibility_checker

**Subfase.** `P0.S8`
**Recebe.** `validated_phase_registry`, `contract_registry`, `schema_registry`, `release_manifest_previous`
**Produz.** `version_compatibility_report`
**Validações.** `schema_version_compatible`, `pipeline_version_consistent`
**Falha rápida.** `version_compatibility_checker_critical_failure`

## P0.S8.M02 — release_manifest_builder

**Subfase.** `P0.S8`
**Recebe.** `pipeline_health_report`, `version_compatibility_report`, `zero_trust_evidence_package`
**Produz.** `release_manifest`
**Validações.** `release_manifest_traceable`, `release_artifacts_listed`
**Falha rápida.** `release_manifest_builder_critical_failure`

## P0.S8.M03 — release_gate_decision_engine

**Subfase.** `P0.S8`
**Recebe.** `release_manifest`, `global_test_report`, `forbidden_connection_report`, `code_quality_report`, `hash_integrity_report`
**Produz.** `release_gate_report`
**Validações.** `fail_on_forbidden_connection`, `fail_on_critical_test_failure`
**Falha rápida.** `release_gate_decision_engine_critical_failure`

## P0.S9.M01 — phase_feedback_router

**Subfase.** `P0.S9`
**Recebe.** `release_gate_report`, `phase_health_panel`, `code_quality_report`, `global_test_report`
**Produz.** `phase_zero_trust_feedback_panel`
**Validações.** `feedback_per_phase`, `blocking_vs_warning_separated`
**Falha rápida.** `phase_feedback_router_critical_failure`

## P0.S9.M02 — blocking_issue_dispatcher

**Subfase.** `P0.S9`
**Recebe.** `phase_zero_trust_feedback_panel`
**Produz.** `blocking_issue_report`
**Validações.** `blocking_errors_have_owner`, `blocking_errors_have_action`
**Falha rápida.** `blocking_issue_dispatcher_critical_failure`

## P0.S9.M03 — nonblocking_warning_dispatcher

**Subfase.** `P0.S9`
**Recebe.** `phase_zero_trust_feedback_panel`
**Produz.** `nonblocking_warning_report`
**Validações.** `warnings_have_owner`, `warnings_not_release_blocking`
**Falha rápida.** `nonblocking_warning_dispatcher_critical_failure`

## P0.S9.M04 — zero_trust_feedback_manifest_builder

**Subfase.** `P0.S9`
**Recebe.** `blocking_issue_report`, `nonblocking_warning_report`, `phase_zero_trust_feedback_panel`
**Produz.** `zero_trust_feedback_manifest`
**Validações.** `feedback_manifest_complete`, `phase_feedback_traceable`
**Falha rápida.** `zero_trust_feedback_manifest_builder_critical_failure`
