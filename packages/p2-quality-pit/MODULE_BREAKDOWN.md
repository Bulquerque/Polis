# MODULE_BREAKDOWN — phase_02_quality_pit — RC4.1

Este arquivo substitui a decomposição anterior com o desenho corrigido pelas auditorias de módulos.

## P2.S1.M01 — phase1_handoff_validator

**Função.** Validar pacote completo da Fase 1 antes de qualquer leitura.

**Recebe.** `handoff_manifest_to_phase_2, source_registry, raw_file_inventory, source_snapshot_registry, raw_readability_report, raw_schema_hint_report, ingestion_error_report`

**Produz.** `validated_phase1_handoff_bundle`

**Validações.** `all_phase1_outputs_present, hashes_match`

**Fail-fast.** `phase1_handoff_validator_schema_violation, phase1_handoff_validator_forbidden_field_detected`

## P2.S1.M02 — raw_artifact_reader

**Função.** Ler artefatos brutos validados preservando lineage.

**Recebe.** `validated_phase1_handoff_bundle`

**Produz.** `raw_artifact_read_bundle`

**Validações.** `readability_status_ok, lineage_preserved`

**Fail-fast.** `raw_artifact_reader_schema_violation, raw_artifact_reader_forbidden_field_detected`

## P2.S1.M03 — source_quality_panel_builder

**Função.** Consolidar qualidade por fonte a partir de readability, erros e status de ingestão.

**Recebe.** `validated_phase1_handoff_bundle, raw_readability_report, ingestion_error_report`

**Produz.** `source_quality_panel`

**Validações.** `source_quality_score_present, critical_source_flags_present`

**Fail-fast.** `source_quality_panel_builder_schema_violation, source_quality_panel_builder_forbidden_field_detected`

## P2.S2.M01 — temporal_availability_normalizer

**Função.** Normalizar available_at/as_of_date de forma point-in-time sem olhar futuro.

**Recebe.** `raw_artifact_read_bundle, source_quality_panel`

**Produz.** `pit_normalized_raw_bundle`

**Validações.** `available_at_required, no_future_availability`

**Fail-fast.** `temporal_availability_normalizer_schema_violation, temporal_availability_normalizer_forbidden_field_detected`

## P2.S2.M02 — identifier_key_harmonizer

**Função.** Harmonizar identificadores, tickers e contract_key determinístico sem instrumento sintético.

**Recebe.** `pit_normalized_raw_bundle`

**Produz.** `identifier_harmonized_bundle`

**Validações.** `contract_key_deterministic, no_synthetic_instrument`

**Fail-fast.** `identifier_key_harmonizer_schema_violation, identifier_key_harmonizer_forbidden_field_detected`

## P2.S3.M01 — macro_panel_cleaner

**Função.** Limpar macro BR/US em painéis PIT sem criar features.

**Recebe.** `identifier_harmonized_bundle, source_quality_panel`

**Produz.** `clean_macro_br_panel, clean_macro_us_panel`

**Validações.** `macro_dates_pit, no_target_creation`

**Fail-fast.** `macro_panel_cleaner_schema_violation, macro_panel_cleaner_forbidden_field_detected`

## P2.S3.M02 — benchmark_panel_cleaner

**Função.** Limpar benchmarks/mercado em painel PIT.

**Recebe.** `identifier_harmonized_bundle, source_quality_panel`

**Produz.** `clean_benchmark_panel`

**Validações.** `benchmark_key_unique, no_prediction`

**Fail-fast.** `benchmark_panel_cleaner_schema_violation, benchmark_panel_cleaner_forbidden_field_detected`

## P2.S3.M03 — calendar_panel_builder

**Função.** Construir calendário negociável e calendário de fonte/mercado.

**Recebe.** `identifier_harmonized_bundle, source_quality_panel`

**Produz.** `clean_calendar_panel`

**Validações.** `calendar_dates_unique, trading_day_flag_present`

**Fail-fast.** `calendar_panel_builder_schema_violation, calendar_panel_builder_forbidden_field_detected`

## P2.S3.M04 — corporate_actions_cleaner

**Função.** Limpar eventos corporativos/fatores com disponibilidade PIT.

**Recebe.** `identifier_harmonized_bundle, source_quality_panel, clean_calendar_panel`

**Produz.** `clean_corporate_actions_panel`

**Validações.** `corporate_action_available_at_present, adjustment_factor_not_future`

**Fail-fast.** `corporate_actions_cleaner_schema_violation, corporate_actions_cleaner_forbidden_field_detected`

## P2.S3.M05 — underlying_panel_cleaner

**Função.** Limpar painel de underlyings usando corporate actions e calendário já limpos.

**Recebe.** `identifier_harmonized_bundle, source_quality_panel, clean_calendar_panel, clean_corporate_actions_panel`

**Produz.** `clean_underlying_panel`

**Validações.** `underlying_date_unique, price_non_negative, corporate_actions_applied_pit`

**Fail-fast.** `underlying_panel_cleaner_schema_violation, underlying_panel_cleaner_forbidden_field_detected`

## P2.S3.M06 — underlying_trade_panel_builder

**Função.** Construir painel negociável de underlying para Fase 6, sem candidato.

**Recebe.** `clean_underlying_panel, clean_calendar_panel, source_quality_panel`

**Produz.** `clean_underlying_trade_panel`

**Validações.** `tradable_price_present, calendar_aligned, no_candidate_creation`

**Fail-fast.** `underlying_trade_panel_builder_schema_violation, underlying_trade_panel_builder_forbidden_field_detected`

## P2.S4.M01 — option_contract_parser

**Função.** Extrair contratos reais de opções com option_id, expiration, strike e contract_key.

**Recebe.** `identifier_harmonized_bundle, clean_calendar_panel, source_quality_panel`

**Produz.** `clean_option_contract_panel`

**Validações.** `option_id_present, expiration_date_present, strike_present, contract_key_present`

**Fail-fast.** `option_contract_parser_schema_violation, option_contract_parser_forbidden_field_detected`

## P2.S4.M02 — option_quote_cleaner

**Função.** Limpar quotes de opções ligados a contratos reais sem criar candidato.

**Recebe.** `identifier_harmonized_bundle, clean_option_contract_panel, source_quality_panel`

**Produz.** `clean_option_quotes_panel`

**Validações.** `quote_has_contract_key, no_score`

**Fail-fast.** `option_quote_cleaner_schema_violation, option_quote_cleaner_forbidden_field_detected`

## P2.S4.M03 — cost_liquidity_reference_builder

**Função.** Construir referências de custo e liquidez para underlying/opções, sem execução.

**Recebe.** `clean_option_quotes_panel, clean_underlying_panel, clean_underlying_trade_panel, source_quality_panel`

**Produz.** `clean_cost_reference_panel, clean_liquidity_reference_panel`

**Validações.** `cost_reference_present, liquidity_reference_present, no_trade_decision`

**Fail-fast.** `cost_liquidity_reference_builder_schema_violation, cost_liquidity_reference_builder_forbidden_field_detected`

## P2.S5.M01 — context_document_event_cleaner

**Função.** Limpar documentos, fontes contextuais e eventos para Fase 3.

**Recebe.** `identifier_harmonized_bundle, source_quality_panel`

**Produz.** `clean_context_source_panel, clean_document_panel, clean_event_reference_panel`

**Validações.** `document_available_at_present, no_trade_signal`

**Fail-fast.** `context_document_event_cleaner_schema_violation, context_document_event_cleaner_forbidden_field_detected`

## P2.S6.M01 — quality_report_phase2_builder

**Função.** Gerar relatório global de qualidade cobrindo todos os painéis oficiais da Fase 2.

**Recebe.** `source_quality_panel, clean_context_source_panel, clean_document_panel, clean_event_reference_panel, clean_underlying_panel, clean_underlying_trade_panel, clean_macro_br_panel, clean_macro_us_panel, clean_benchmark_panel, clean_calendar_panel, clean_corporate_actions_panel, clean_option_contract_panel, clean_option_quotes_panel, clean_cost_reference_panel, clean_liquidity_reference_panel`

**Produz.** `quality_report_phase_2`

**Validações.** `all_official_panels_covered, quality_flags_summarized`

**Fail-fast.** `quality_report_phase2_builder_schema_violation, quality_report_phase2_builder_forbidden_field_detected`

## P2.S6.M02 — multi_phase_handoff_packager

**Função.** Criar manifests de handoff para Fases 3, 4 e 6, sem bundles opacos.

**Recebe.** `clean_context_source_panel, clean_document_panel, clean_event_reference_panel, source_quality_panel, quality_report_phase_2, clean_underlying_panel, clean_underlying_trade_panel, clean_macro_br_panel, clean_macro_us_panel, clean_benchmark_panel, clean_calendar_panel, clean_corporate_actions_panel, clean_option_quotes_panel, clean_option_contract_panel, clean_cost_reference_panel, clean_liquidity_reference_panel`

**Produz.** `context_handoff_manifest, phase3_handoff_manifest, phase4_handoff_manifest, phase6_handoff_manifest`

**Validações.** `handoff_manifest_references_existing_artifacts, no_hidden_bundle`

**Fail-fast.** `multi_phase_handoff_packager_schema_violation, multi_phase_handoff_packager_forbidden_field_detected`
