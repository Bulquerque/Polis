# SUBPHASES — phase_01_ingestion — RC4.1

Subfases revisadas com módulos corrigidos e relações internas explícitas.

## P1.S1

Módulos: `P1.S1.M01`, `P1.S1.M02`, `P1.S1.M03`

Entradas agregadas: `source_registry_config`, `api_source_definitions`, `manual_source_definitions`, `ingestion_run_config`, `source_credentials_handle`, `source_calendar_config`, `source_registry`, `validated_ingestion_run_config`, `local_raw_file_paths`

Saídas agregadas: `source_registry`, `validated_ingestion_run_config`, `source_capture_plan`

## P1.S2

Módulos: `P1.S2.M01`, `P1.S2.M02`, `P1.S2.M03`, `P1.S2.M04`, `P1.S2.M05`, `P1.S2.M06`, `P1.S2.M07`

Entradas agregadas: `source_capture_plan`, `capture_task_manifest`, `macro_raw_capture_inventory`, `benchmark_raw_capture_inventory`, `crypto_raw_capture_inventory`, `document_raw_capture_inventory`

Saídas agregadas: `capture_task_manifest`, `b3_raw_capture_inventory`, `macro_raw_capture_inventory`, `benchmark_raw_capture_inventory`, `crypto_raw_capture_inventory`, `document_raw_capture_inventory`, `non_b3_raw_capture_inventory`

## P1.S3

Módulos: `P1.S3.M01`, `P1.S3.M02`

Entradas agregadas: `b3_raw_capture_inventory`, `non_b3_raw_capture_inventory`, `raw_file_inventory`, `raw_artifact_store`

Saídas agregadas: `raw_file_inventory`, `raw_artifact_store`, `versioned_raw_file_inventory`

## P1.S4

Módulos: `P1.S4.M01`, `P1.S4.M02`

Entradas agregadas: `versioned_raw_file_inventory`, `raw_readability_report`

Saídas agregadas: `raw_readability_report`, `raw_schema_hint_report`

## P1.S5

Módulos: `P1.S5.M01`, `P1.S5.M02`, `P1.S5.M03`, `P1.S5.M04`

Entradas agregadas: `source_registry`, `capture_task_manifest`, `versioned_raw_file_inventory`, `raw_readability_report`, `raw_schema_hint_report`, `ingestion_manifest`, `source_snapshot_registry`, `ingestion_error_report`

Saídas agregadas: `ingestion_manifest`, `source_snapshot_registry`, `ingestion_error_report`, `handoff_manifest_to_phase_2`, `source_registry`, `raw_file_inventory`, `raw_readability_report`, `raw_schema_hint_report`
