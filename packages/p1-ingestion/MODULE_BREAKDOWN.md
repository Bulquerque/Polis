# MODULE_BREAKDOWN — phase_01_ingestion — RC4.1

Este arquivo substitui a decomposição anterior com o desenho corrigido pelas auditorias de módulos.

## P1.S1.M01 — source_registry_loader

**Função.** Carregar source_registry_config, api_source_definitions e manual_source_definitions em catálogo único de fontes permitidas.

**Recebe.** `source_registry_config, api_source_definitions, manual_source_definitions`

**Produz.** `source_registry`

**Validações.** `source_id_unique, source_type_allowed, manual_and_api_sources_explicit`

**Fail-fast.** `source_registry_loader_schema_violation, source_registry_loader_forbidden_field_detected`

## P1.S1.M02 — ingestion_run_config_validator

**Função.** Validar run config, credenciais indiretas e calendário sem materializar segredo.

**Recebe.** `ingestion_run_config, source_credentials_handle, source_calendar_config, source_registry`

**Produz.** `validated_ingestion_run_config`

**Validações.** `run_id_present, credentials_not_materialized, calendar_declared`

**Fail-fast.** `ingestion_run_config_validator_schema_violation, ingestion_run_config_validator_forbidden_field_detected`

## P1.S1.M03 — source_availability_planner

**Função.** Planejar disponibilidade e tarefas de captura por fonte sem baixar dados ainda.

**Recebe.** `validated_ingestion_run_config, source_registry, source_calendar_config, local_raw_file_paths`

**Produz.** `source_capture_plan`

**Validações.** `source_plan_complete, critical_sources_marked`

**Fail-fast.** `source_availability_planner_schema_violation, source_availability_planner_forbidden_field_detected`

## P1.S2.M01 — source_capture_orchestrator

**Função.** Transformar plano de captura em tarefas explícitas e rastreáveis.

**Recebe.** `source_capture_plan`

**Produz.** `capture_task_manifest`

**Validações.** `capture_task_has_source_id, task_lineage_declared`

**Fail-fast.** `source_capture_orchestrator_schema_violation, source_capture_orchestrator_forbidden_field_detected`

## P1.S2.M02 — b3_cotahist_raw_fetcher

**Função.** Capturar dados B3/COTAHIST brutos preservando bytes originais.

**Recebe.** `capture_task_manifest`

**Produz.** `b3_raw_capture_inventory`

**Validações.** `raw_bytes_preserved, no_economic_cleaning`

**Fail-fast.** `b3_cotahist_raw_fetcher_schema_violation, b3_cotahist_raw_fetcher_forbidden_field_detected`

## P1.S2.M03 — macro_raw_fetcher

**Função.** Capturar fontes macro brutas sem harmonização econômica.

**Recebe.** `capture_task_manifest`

**Produz.** `macro_raw_capture_inventory`

**Validações.** `raw_bytes_preserved, source_id_present`

**Fail-fast.** `macro_raw_fetcher_schema_violation, macro_raw_fetcher_forbidden_field_detected`

## P1.S2.M04 — benchmark_raw_fetcher

**Função.** Capturar benchmarks/mercado brutos sem ajuste ou feature.

**Recebe.** `capture_task_manifest`

**Produz.** `benchmark_raw_capture_inventory`

**Validações.** `raw_bytes_preserved, source_id_present`

**Fail-fast.** `benchmark_raw_fetcher_schema_violation, benchmark_raw_fetcher_forbidden_field_detected`

## P1.S2.M05 — crypto_raw_fetcher

**Função.** Capturar fontes cripto/alternativas brutas sem normalização de sinal.

**Recebe.** `capture_task_manifest`

**Produz.** `crypto_raw_capture_inventory`

**Validações.** `raw_bytes_preserved, source_id_present`

**Fail-fast.** `crypto_raw_fetcher_schema_violation, crypto_raw_fetcher_forbidden_field_detected`

## P1.S2.M06 — document_raw_collector

**Função.** Capturar documentos/textos brutos mantendo referência de fonte e disponibilidade.

**Recebe.** `capture_task_manifest`

**Produz.** `document_raw_capture_inventory`

**Validações.** `raw_text_or_file_preserved, source_available_at_declared`

**Fail-fast.** `document_raw_collector_schema_violation, document_raw_collector_forbidden_field_detected`

## P1.S2.M07 — non_b3_capture_inventory_assembler

**Função.** Consolidar inventários macro, benchmark, cripto e documento em um inventário não-B3.

**Recebe.** `macro_raw_capture_inventory, benchmark_raw_capture_inventory, crypto_raw_capture_inventory, document_raw_capture_inventory`

**Produz.** `non_b3_raw_capture_inventory`

**Validações.** `all_non_b3_sources_accounted, no_cleaning`

**Fail-fast.** `non_b3_capture_inventory_assembler_schema_violation, non_b3_capture_inventory_assembler_forbidden_field_detected`

## P1.S3.M01 — raw_artifact_writer

**Função.** Escrever artefatos raw em storage imutável sem overwrite.

**Recebe.** `b3_raw_capture_inventory, non_b3_raw_capture_inventory`

**Produz.** `raw_file_inventory, raw_artifact_store`

**Validações.** `no_overwrite, artifact_path_exists`

**Fail-fast.** `raw_artifact_writer_schema_violation, raw_artifact_writer_forbidden_field_detected`

## P1.S3.M02 — hash_version_manager

**Função.** Calcular hash, tamanho e versão para cada artefato raw.

**Recebe.** `raw_file_inventory, raw_artifact_store`

**Produz.** `versioned_raw_file_inventory`

**Validações.** `hash_present, file_size_positive, artifact_id_unique`

**Fail-fast.** `hash_version_manager_schema_violation, hash_version_manager_forbidden_field_detected`

## P1.S4.M01 — raw_readability_checker

**Função.** Checar legibilidade mínima sem interpretar economicamente dados.

**Recebe.** `versioned_raw_file_inventory`

**Produz.** `raw_readability_report`

**Validações.** `readability_status_present, empty_file_flagged`

**Fail-fast.** `raw_readability_checker_schema_violation, raw_readability_checker_forbidden_field_detected`

## P1.S4.M02 — raw_schema_hint_detector

**Função.** Gerar hints de schema bruto, sem schema limpo ou transformação.

**Recebe.** `versioned_raw_file_inventory, raw_readability_report`

**Produz.** `raw_schema_hint_report`

**Validações.** `schema_hint_not_clean_schema`

**Fail-fast.** `raw_schema_hint_detector_schema_violation, raw_schema_hint_detector_forbidden_field_detected`

## P1.S5.M01 — ingestion_manifest_builder

**Função.** Construir manifesto de ingestão com artefatos escritos, tarefas tentadas, puladas e falhas.

**Recebe.** `source_registry, capture_task_manifest, versioned_raw_file_inventory, raw_readability_report, raw_schema_hint_report`

**Produz.** `ingestion_manifest`

**Validações.** `all_attempted_tasks_accounted, lineage_complete`

**Fail-fast.** `ingestion_manifest_builder_schema_violation, ingestion_manifest_builder_forbidden_field_detected`

## P1.S5.M02 — source_snapshot_registry_builder

**Função.** Registrar snapshot de fonte/versionamento por source_id e run.

**Recebe.** `source_registry, ingestion_manifest, versioned_raw_file_inventory`

**Produz.** `source_snapshot_registry`

**Validações.** `source_snapshot_unique, snapshot_references_hash`

**Fail-fast.** `source_snapshot_registry_builder_schema_violation, source_snapshot_registry_builder_forbidden_field_detected`

## P1.S5.M03 — ingestion_error_report_builder

**Função.** Gerar relatório explícito de erros e warnings sem falha silenciosa.

**Recebe.** `ingestion_manifest, raw_readability_report, capture_task_manifest`

**Produz.** `ingestion_error_report`

**Validações.** `critical_error_explicit, no_silent_failure`

**Fail-fast.** `ingestion_error_report_builder_schema_violation, ingestion_error_report_builder_forbidden_field_detected`

## P1.S5.M04 — phase2_handoff_packager

**Função.** Empacotar handoff oficial para Fase 2 com todos os produtores reais declarados.

**Recebe.** `ingestion_manifest, source_registry, source_snapshot_registry, versioned_raw_file_inventory, raw_readability_report, raw_schema_hint_report, ingestion_error_report`

**Produz.** `handoff_manifest_to_phase_2, source_registry, raw_file_inventory, source_snapshot_registry, raw_readability_report, raw_schema_hint_report, ingestion_error_report`

**Validações.** `all_phase2_outputs_present, hashes_present, no_blocking_error_open`

**Fail-fast.** `phase2_handoff_packager_schema_violation, phase2_handoff_packager_forbidden_field_detected`
