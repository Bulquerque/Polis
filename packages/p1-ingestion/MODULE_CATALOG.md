# MODULE_CATALOG — phase_01_ingestion — RC4.1

Módulos oficiais após correção módulo a módulo. Cada módulo tem inputs, outputs, validações e produtores/consumidores explícitos.

## P1.S1.M01 — source_registry_loader

- Subfase: `P1.S1`

- Função: Carregar source_registry_config, api_source_definitions e manual_source_definitions em catálogo único de fontes permitidas.

- Inputs: `source_registry_config, api_source_definitions, manual_source_definitions`

- Outputs: `source_registry`

## P1.S1.M02 — ingestion_run_config_validator

- Subfase: `P1.S1`

- Função: Validar run config, credenciais indiretas e calendário sem materializar segredo.

- Inputs: `ingestion_run_config, source_credentials_handle, source_calendar_config, source_registry`

- Outputs: `validated_ingestion_run_config`

## P1.S1.M03 — source_availability_planner

- Subfase: `P1.S1`

- Função: Planejar disponibilidade e tarefas de captura por fonte sem baixar dados ainda.

- Inputs: `validated_ingestion_run_config, source_registry, source_calendar_config, local_raw_file_paths`

- Outputs: `source_capture_plan`

## P1.S2.M01 — source_capture_orchestrator

- Subfase: `P1.S2`

- Função: Transformar plano de captura em tarefas explícitas e rastreáveis.

- Inputs: `source_capture_plan`

- Outputs: `capture_task_manifest`

## P1.S2.M02 — b3_cotahist_raw_fetcher

- Subfase: `P1.S2`

- Função: Capturar dados B3/COTAHIST brutos preservando bytes originais.

- Inputs: `capture_task_manifest`

- Outputs: `b3_raw_capture_inventory`

## P1.S2.M03 — macro_raw_fetcher

- Subfase: `P1.S2`

- Função: Capturar fontes macro brutas sem harmonização econômica.

- Inputs: `capture_task_manifest`

- Outputs: `macro_raw_capture_inventory`

## P1.S2.M04 — benchmark_raw_fetcher

- Subfase: `P1.S2`

- Função: Capturar benchmarks/mercado brutos sem ajuste ou feature.

- Inputs: `capture_task_manifest`

- Outputs: `benchmark_raw_capture_inventory`

## P1.S2.M05 — crypto_raw_fetcher

- Subfase: `P1.S2`

- Função: Capturar fontes cripto/alternativas brutas sem normalização de sinal.

- Inputs: `capture_task_manifest`

- Outputs: `crypto_raw_capture_inventory`

## P1.S2.M06 — document_raw_collector

- Subfase: `P1.S2`

- Função: Capturar documentos/textos brutos mantendo referência de fonte e disponibilidade.

- Inputs: `capture_task_manifest`

- Outputs: `document_raw_capture_inventory`

## P1.S2.M07 — non_b3_capture_inventory_assembler

- Subfase: `P1.S2`

- Função: Consolidar inventários macro, benchmark, cripto e documento em um inventário não-B3.

- Inputs: `macro_raw_capture_inventory, benchmark_raw_capture_inventory, crypto_raw_capture_inventory, document_raw_capture_inventory`

- Outputs: `non_b3_raw_capture_inventory`

## P1.S3.M01 — raw_artifact_writer

- Subfase: `P1.S3`

- Função: Escrever artefatos raw em storage imutável sem overwrite.

- Inputs: `b3_raw_capture_inventory, non_b3_raw_capture_inventory`

- Outputs: `raw_file_inventory, raw_artifact_store`

## P1.S3.M02 — hash_version_manager

- Subfase: `P1.S3`

- Função: Calcular hash, tamanho e versão para cada artefato raw.

- Inputs: `raw_file_inventory, raw_artifact_store`

- Outputs: `versioned_raw_file_inventory`

## P1.S4.M01 — raw_readability_checker

- Subfase: `P1.S4`

- Função: Checar legibilidade mínima sem interpretar economicamente dados.

- Inputs: `versioned_raw_file_inventory`

- Outputs: `raw_readability_report`

## P1.S4.M02 — raw_schema_hint_detector

- Subfase: `P1.S4`

- Função: Gerar hints de schema bruto, sem schema limpo ou transformação.

- Inputs: `versioned_raw_file_inventory, raw_readability_report`

- Outputs: `raw_schema_hint_report`

## P1.S5.M01 — ingestion_manifest_builder

- Subfase: `P1.S5`

- Função: Construir manifesto de ingestão com artefatos escritos, tarefas tentadas, puladas e falhas.

- Inputs: `source_registry, capture_task_manifest, versioned_raw_file_inventory, raw_readability_report, raw_schema_hint_report`

- Outputs: `ingestion_manifest`

## P1.S5.M02 — source_snapshot_registry_builder

- Subfase: `P1.S5`

- Função: Registrar snapshot de fonte/versionamento por source_id e run.

- Inputs: `source_registry, ingestion_manifest, versioned_raw_file_inventory`

- Outputs: `source_snapshot_registry`

## P1.S5.M03 — ingestion_error_report_builder

- Subfase: `P1.S5`

- Função: Gerar relatório explícito de erros e warnings sem falha silenciosa.

- Inputs: `ingestion_manifest, raw_readability_report, capture_task_manifest`

- Outputs: `ingestion_error_report`

## P1.S5.M04 — phase2_handoff_packager

- Subfase: `P1.S5`

- Função: Empacotar handoff oficial para Fase 2 com todos os produtores reais declarados.

- Inputs: `ingestion_manifest, source_registry, source_snapshot_registry, versioned_raw_file_inventory, raw_readability_report, raw_schema_hint_report, ingestion_error_report`

- Outputs: `handoff_manifest_to_phase_2, source_registry, raw_file_inventory, source_snapshot_registry, raw_readability_report, raw_schema_hint_report, ingestion_error_report`
