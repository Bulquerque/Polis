# MODULE_CATALOG — phase_02_quality_pit — RC4.1

Módulos oficiais após correção módulo a módulo. Cada módulo tem inputs, outputs, validações e produtores/consumidores explícitos.

## P2.S1.M01 — phase1_handoff_validator

- Subfase: `P2.S1`

- Função: Validar pacote completo da Fase 1 antes de qualquer leitura.

- Inputs: `handoff_manifest_to_phase_2, source_registry, raw_file_inventory, source_snapshot_registry, raw_readability_report, raw_schema_hint_report, ingestion_error_report`

- Outputs: `validated_phase1_handoff_bundle`

## P2.S1.M02 — raw_artifact_reader

- Subfase: `P2.S1`

- Função: Ler artefatos brutos validados preservando lineage.

- Inputs: `validated_phase1_handoff_bundle`

- Outputs: `raw_artifact_read_bundle`

## P2.S1.M03 — source_quality_panel_builder

- Subfase: `P2.S1`

- Função: Consolidar qualidade por fonte a partir de readability, erros e status de ingestão.

- Inputs: `validated_phase1_handoff_bundle, raw_readability_report, ingestion_error_report`

- Outputs: `source_quality_panel`

## P2.S2.M01 — temporal_availability_normalizer

- Subfase: `P2.S2`

- Função: Normalizar available_at/as_of_date de forma point-in-time sem olhar futuro.

- Inputs: `raw_artifact_read_bundle, source_quality_panel`

- Outputs: `pit_normalized_raw_bundle`

## P2.S2.M02 — identifier_key_harmonizer

- Subfase: `P2.S2`

- Função: Harmonizar identificadores, tickers e contract_key determinístico sem instrumento sintético.

- Inputs: `pit_normalized_raw_bundle`

- Outputs: `identifier_harmonized_bundle`

## P2.S3.M01 — macro_panel_cleaner

- Subfase: `P2.S3`

- Função: Limpar macro BR/US em painéis PIT sem criar features.

- Inputs: `identifier_harmonized_bundle, source_quality_panel`

- Outputs: `clean_macro_br_panel, clean_macro_us_panel`

## P2.S3.M02 — benchmark_panel_cleaner

- Subfase: `P2.S3`

- Função: Limpar benchmarks/mercado em painel PIT.

- Inputs: `identifier_harmonized_bundle, source_quality_panel`

- Outputs: `clean_benchmark_panel`

## P2.S3.M03 — calendar_panel_builder

- Subfase: `P2.S3`

- Função: Construir calendário negociável e calendário de fonte/mercado.

- Inputs: `identifier_harmonized_bundle, source_quality_panel`

- Outputs: `clean_calendar_panel`

## P2.S3.M04 — corporate_actions_cleaner

- Subfase: `P2.S3`

- Função: Limpar eventos corporativos/fatores com disponibilidade PIT.

- Inputs: `identifier_harmonized_bundle, source_quality_panel, clean_calendar_panel`

- Outputs: `clean_corporate_actions_panel`

## P2.S3.M05 — underlying_panel_cleaner

- Subfase: `P2.S3`

- Função: Limpar painel de underlyings usando corporate actions e calendário já limpos.

- Inputs: `identifier_harmonized_bundle, source_quality_panel, clean_calendar_panel, clean_corporate_actions_panel`

- Outputs: `clean_underlying_panel`

## P2.S3.M06 — underlying_trade_panel_builder

- Subfase: `P2.S3`

- Função: Construir painel negociável de underlying para Fase 6, sem candidato.

- Inputs: `clean_underlying_panel, clean_calendar_panel, source_quality_panel`

- Outputs: `clean_underlying_trade_panel`

## P2.S4.M01 — option_contract_parser

- Subfase: `P2.S4`

- Função: Extrair contratos reais de opções com option_id, expiration, strike e contract_key.

- Inputs: `identifier_harmonized_bundle, clean_calendar_panel, source_quality_panel`

- Outputs: `clean_option_contract_panel`

## P2.S4.M02 — option_quote_cleaner

- Subfase: `P2.S4`

- Função: Limpar quotes de opções ligados a contratos reais sem criar candidato.

- Inputs: `identifier_harmonized_bundle, clean_option_contract_panel, source_quality_panel`

- Outputs: `clean_option_quotes_panel`

## P2.S4.M03 — cost_liquidity_reference_builder

- Subfase: `P2.S4`

- Função: Construir referências de custo e liquidez para underlying/opções, sem execução.

- Inputs: `clean_option_quotes_panel, clean_underlying_panel, clean_underlying_trade_panel, source_quality_panel`

- Outputs: `clean_cost_reference_panel, clean_liquidity_reference_panel`

## P2.S5.M01 — context_document_event_cleaner

- Subfase: `P2.S5`

- Função: Limpar documentos, fontes contextuais e eventos para Fase 3.

- Inputs: `identifier_harmonized_bundle, source_quality_panel`

- Outputs: `clean_context_source_panel, clean_document_panel, clean_event_reference_panel`

## P2.S6.M01 — quality_report_phase2_builder

- Subfase: `P2.S6`

- Função: Gerar relatório global de qualidade cobrindo todos os painéis oficiais da Fase 2.

- Inputs: `source_quality_panel, clean_context_source_panel, clean_document_panel, clean_event_reference_panel, clean_underlying_panel, clean_underlying_trade_panel, clean_macro_br_panel, clean_macro_us_panel, clean_benchmark_panel, clean_calendar_panel, clean_corporate_actions_panel, clean_option_contract_panel, clean_option_quotes_panel, clean_cost_reference_panel, clean_liquidity_reference_panel`

- Outputs: `quality_report_phase_2`

## P2.S6.M02 — multi_phase_handoff_packager

- Subfase: `P2.S6`

- Função: Criar manifests de handoff para Fases 3, 4 e 6, sem bundles opacos.

- Inputs: `clean_context_source_panel, clean_document_panel, clean_event_reference_panel, source_quality_panel, quality_report_phase_2, clean_underlying_panel, clean_underlying_trade_panel, clean_macro_br_panel, clean_macro_us_panel, clean_benchmark_panel, clean_calendar_panel, clean_corporate_actions_panel, clean_option_quotes_panel, clean_option_contract_panel, clean_cost_reference_panel, clean_liquidity_reference_panel`

- Outputs: `context_handoff_manifest, phase3_handoff_manifest, phase4_handoff_manifest, phase6_handoff_manifest`
