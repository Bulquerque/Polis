# SUBPHASES — phase_02_quality_pit — RC4.1

Subfases revisadas com módulos corrigidos e relações internas explícitas.

## P2.S1

Módulos: `P2.S1.M01`, `P2.S1.M02`, `P2.S1.M03`

Entradas agregadas: `handoff_manifest_to_phase_2`, `source_registry`, `raw_file_inventory`, `source_snapshot_registry`, `raw_readability_report`, `raw_schema_hint_report`, `ingestion_error_report`, `validated_phase1_handoff_bundle`

Saídas agregadas: `validated_phase1_handoff_bundle`, `raw_artifact_read_bundle`, `source_quality_panel`

## P2.S2

Módulos: `P2.S2.M01`, `P2.S2.M02`

Entradas agregadas: `raw_artifact_read_bundle`, `source_quality_panel`, `pit_normalized_raw_bundle`

Saídas agregadas: `pit_normalized_raw_bundle`, `identifier_harmonized_bundle`

## P2.S3

Módulos: `P2.S3.M01`, `P2.S3.M02`, `P2.S3.M03`, `P2.S3.M04`, `P2.S3.M05`, `P2.S3.M06`

Entradas agregadas: `identifier_harmonized_bundle`, `source_quality_panel`, `clean_calendar_panel`, `clean_corporate_actions_panel`, `clean_underlying_panel`

Saídas agregadas: `clean_macro_br_panel`, `clean_macro_us_panel`, `clean_benchmark_panel`, `clean_calendar_panel`, `clean_corporate_actions_panel`, `clean_underlying_panel`, `clean_underlying_trade_panel`

## P2.S4

Módulos: `P2.S4.M01`, `P2.S4.M02`, `P2.S4.M03`

Entradas agregadas: `identifier_harmonized_bundle`, `clean_calendar_panel`, `source_quality_panel`, `clean_option_contract_panel`, `clean_option_quotes_panel`, `clean_underlying_panel`, `clean_underlying_trade_panel`

Saídas agregadas: `clean_option_contract_panel`, `clean_option_quotes_panel`, `clean_cost_reference_panel`, `clean_liquidity_reference_panel`

## P2.S5

Módulos: `P2.S5.M01`

Entradas agregadas: `identifier_harmonized_bundle`, `source_quality_panel`

Saídas agregadas: `clean_context_source_panel`, `clean_document_panel`, `clean_event_reference_panel`

## P2.S6

Módulos: `P2.S6.M01`, `P2.S6.M02`

Entradas agregadas: `source_quality_panel`, `clean_context_source_panel`, `clean_document_panel`, `clean_event_reference_panel`, `clean_underlying_panel`, `clean_underlying_trade_panel`, `clean_macro_br_panel`, `clean_macro_us_panel`, `clean_benchmark_panel`, `clean_calendar_panel`, `clean_corporate_actions_panel`, `clean_option_contract_panel`, `clean_option_quotes_panel`, `clean_cost_reference_panel`, `clean_liquidity_reference_panel`, `quality_report_phase_2`

Saídas agregadas: `quality_report_phase_2`, `context_handoff_manifest`, `phase3_handoff_manifest`, `phase4_handoff_manifest`, `phase6_handoff_manifest`
