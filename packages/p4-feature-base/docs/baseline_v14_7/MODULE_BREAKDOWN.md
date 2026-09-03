# Module breakdown V14.6-RC1

Total: **49 módulos** em 9 subfases.

## P4.S1 — Autoridade de fronteira

### P4.S1.M01 — `phase2_handoff_validator`
Validar o bundle P2→P4, seus manifests, hashes, versões, grains, cobertura e temporalidade declarada.
- Entradas: p2_required_bundle, p2_extension_bundle
- Saídas: validated_phase2_bundle
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S1.M02 — `phase3_handoff_validator`
Validar o bundle interpretativo P3→P4 sem achatar evidência, disagreement, memória e hipóteses.
- Entradas: p3_required_bundle
- Saídas: validated_phase3_bundle
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S1.M03 — `boundary_consistency_gate`
Fechar run_id, cycle_id, universe_id, as_of_time, versões e consistência cruzada dos handoffs P2 e P3.
- Entradas: validated_phase2_bundle, validated_phase3_bundle
- Saídas: validated_p4_boundary_bundle
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S1.M04 — `n_plus_1_variable_evolution_intake`
Admitir propostas de evolução de variáveis apenas no ciclo N+1, sem otimizar features nem promover mudanças automaticamente.
- Entradas: variable_evolution_input_manifest_optional, validated_p4_boundary_bundle
- Saídas: observer_change_proposal_registry
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S2 — Autoridade temporal e painel canônico

### P4.S2.M01 — `temporal_semantics_resolver`
Resolver event_time, reference_time, published_at, available_at, ingested_at, decision_time e calculation_time.
- Entradas: validated_p4_boundary_bundle
- Saídas: temporally_resolved_observation_bundle
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S2.M02 — `entity_calendar_corporate_action_aligner`
Harmonizar entity_id, underlying, venue, moeda, timezone, sessões, calendários e corporate actions.
- Entradas: temporally_resolved_observation_bundle
- Saídas: entity_aligned_observation_bundle
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S2.M03 — `revision_freshness_missingness_mapper`
Classificar vintage, revisão, staleness, cobertura, ausência estrutural, atraso e falha de fonte sem converter missing em zero.
- Entradas: entity_aligned_observation_bundle
- Saídas: availability_missingness_panel, quality_enriched_observation_bundle
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S2.M04 — `canonical_observation_store_builder`
Construir painel longo canônico e point-in-time para todos os cálculos posteriores.
- Entradas: quality_enriched_observation_bundle, availability_missingness_panel
- Saídas: canonical_observation_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S3 — Governança de hipóteses, observadores e operadores

### P4.S3.M01 — `phenomenon_perspective_registry`
Registrar fenômenos, perspectivas, modalidades, mecanismos, horizontes, falhas conhecidas e regimes esperados.
- Entradas: observer_change_proposal_registry
- Saídas: feature_observer_registry, feature_parameter_policy_registry
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S3.M02 — `observer_spec_validator`
Validar receitas declarativas de observadores, dependências, janelas, lags, grains e políticas de disponibilidade.
- Entradas: feature_observer_registry, canonical_observation_panel
- Saídas: validated_observer_spec_registry
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S3.M03 — `causal_operator_engine`
Executar operadores temporais univariados causais e reproduzíveis com estados de fit versionados.
- Entradas: validated_observer_spec_registry, canonical_observation_panel
- Saídas: causal_operator_result_panel, operator_fit_state_registry
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S3.M04 — `relational_stateful_operator_engine`
Executar beta, correlação, residual, spread, lead-lag, cluster distance e agregações de grafo sem leakage.
- Entradas: validated_observer_spec_registry, canonical_observation_panel
- Saídas: relational_operator_result_panel, relational_fit_state_registry
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S3.M05 — `hypothesis_passport_budget_gate`
Validar passaportes teóricos, classificar hipóteses por tier e aplicar orçamento hierárquico antes de qualquer cálculo confirmatório.
- Entradas: feature_observer_registry, feature_parameter_policy_registry, observer_change_proposal_registry, foundational_hypothesis_core_registry
- Saídas: approved_hypothesis_passport_registry, hypothesis_budget_report, rejected_hypothesis_registry
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S4 — Fábricas de observações atômicas

### P4.S4.M01 — `price_return_observations`
Produzir retornos, gaps, ranges, posição no range, overnight/sessão e observações de preço ajustado.
- Entradas: canonical_observation_panel, causal_operator_result_panel
- Saídas: price_return_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S4.M02 — `volume_liquidity_microstructure_observations`
Produzir turnover, volume relativo, volume financeiro, Amihud, spread, staleness e impacto aproximado.
- Entradas: canonical_observation_panel, causal_operator_result_panel
- Saídas: liquidity_microstructure_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S4.M03 — `realized_risk_tail_observations`
Produzir volatilidade realizada, semivariância, drawdown, skew, kurtosis, jumps e vol-of-vol.
- Entradas: canonical_observation_panel, causal_operator_result_panel
- Saídas: risk_tail_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S4.M04 — `benchmark_cross_asset_observations`
Produzir retornos relativos, beta histórico, spreads, breadth, dispersão e dependências cross-asset.
- Entradas: canonical_observation_panel, relational_operator_result_panel
- Saídas: benchmark_cross_asset_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S4.M05 — `underlying_option_state_observations`
Agregar option chain ao nível do underlying: IV ATM, skew, smile, term structure, IV-RV, OI e cobertura.
- Entradas: canonical_observation_panel, relational_operator_result_panel
- Saídas: underlying_option_state_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S4.M06 — `macro_event_calendar_observations`
Produzir mudanças macro, vintages, surpresas quando expectativa autorizada existir, curvas, eventos e sazonalidade.
- Entradas: canonical_observation_panel, causal_operator_result_panel
- Saídas: macro_event_calendar_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S4.M07 — `social_evidence_context_observations`
Preservar direção, força, credibilidade, novidade, disagreement, memória, hipóteses e estabilidade narrativa.
- Entradas: canonical_observation_panel, validated_phase3_bundle
- Saídas: social_evidence_context_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S4.M08 — `fundamental_accounting_quality_observations`
Produzir observações point-in-time de valuation, rentabilidade, qualidade, investimento, alavancagem, accruals e evolução contábil, com vintages e disponibilidade explícitos.
- Entradas: canonical_observation_panel, causal_operator_result_panel, validated_phase2_bundle
- Saídas: fundamental_accounting_atomic_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S5 — Fábricas de perspectivas econômicas

### P4.S5.M01 — `momentum_trend_persistence_perspectives`
Construir views de momentum por retorno, slope, breakout, persistência, residual, volume, opções, narrativa e P3.
- Entradas: atomic_observation_bundle
- Saídas: momentum_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M02 — `reversion_relative_value_perspectives`
Construir views de reversão por média, residual, pares, setor, cluster, gap, volume e saturação narrativa.
- Entradas: atomic_observation_bundle
- Saídas: reversion_relative_value_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M03 — `risk_uncertainty_stress_perspectives`
Construir views de risco realizado, implícito, downside, cauda, instabilidade, surpresa e disagreement.
- Entradas: atomic_observation_bundle
- Saídas: risk_uncertainty_stress_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M04 — `liquidity_attention_crowding_perspectives`
Construir views de iliquidez, atenção, concentração, OI, consenso excessivo e crowding.
- Entradas: atomic_observation_bundle
- Saídas: liquidity_attention_crowding_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M05 — `structure_contagion_breadth_perspectives`
Construir views de market mode, effective rank, eigen entropy, centralidade, propagação, dispersão e breadth.
- Entradas: atomic_observation_bundle
- Saídas: structure_contagion_breadth_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M06 — `macro_cycle_regime_state_perspectives`
Descrever estado contemporâneo de inflação, crescimento, liquidez, curva, stress e distância histórica.
- Entradas: atomic_observation_bundle
- Saídas: macro_cycle_regime_state_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M07 — `event_surprise_seasonality_perspectives`
Construir views de tempo até/des­de evento, reação contemporânea, persistência, reversão e sazonalidade.
- Entradas: atomic_observation_bundle
- Saídas: event_surprise_seasonality_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M08 — `narrative_evidence_disagreement_perspectives`
Construir views de consenso, polarização, contradição, novidade, diversidade de hipóteses e visão minoritária.
- Entradas: atomic_observation_bundle
- Saídas: narrative_evidence_disagreement_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M09 — `value_quality_profitability_investment_perspectives`
Construir perspectivas de value, qualidade, profitability, investment, leverage e accruals sem usar retornos futuros para selecionar ou calibrar sinais.
- Entradas: atomic_observation_bundle
- Saídas: value_quality_profitability_investment_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S5.M10 — `carry_curve_basis_perspectives`
Construir perspectivas de carry, roll-down, basis, inclinação e curvatura de estruturas a termo em classes de ativos para as quais os dados existam.
- Entradas: atomic_observation_bundle
- Saídas: carry_curve_basis_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S6 — Fusão, confirmação, conflito e horizontes

### P4.S6.M01 — `multi_view_alignment`
Alinhar perspectivas por entidade, fenômeno, decision_time e horizonte mantendo views ausentes explicitamente.
- Entradas: perspective_family_bundle
- Saídas: aligned_perspective_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S6.M02 — `confirmation_conflict_engine`
Medir consenso, dispersão, entropia, confirmação independente, conflito modal e força de visão minoritária.
- Entradas: aligned_perspective_panel
- Saídas: perspective_conflict_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S6.M03 — `hypothesis_constrained_interaction_builder`
Criar apenas interações registradas com racional econômico, famílias de origem e risco de overfitting.
- Entradas: aligned_perspective_panel, feature_observer_registry
- Saídas: interaction_feature_panel
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S6.M04 — `multi_horizon_missing_view_assembler`
Organizar views e conflitos em conjuntos intraday, short, medium, long e cross-horizon.
- Entradas: aligned_perspective_panel, perspective_conflict_panel, interaction_feature_panel, availability_missingness_panel
- Saídas: horizon_feature_panel, horizon_feature_set_manifest
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S7 — Transformação causal e seleção estrutural

### P4.S7.M01 — `causal_transform_fit_engine`
Aplicar winsorization, log, clipping e scalers com fit_start, fit_end e estado versionado.
- Entradas: horizon_feature_panel
- Saídas: causally_transformed_feature_panel, feature_transform_state_manifest
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S7.M02 — `normalization_neutralization_engine`
Produzir versões rank/z-score e neutralizações por mercado, setor, beta, volatilidade, tamanho e moeda.
- Entradas: causally_transformed_feature_panel
- Saídas: underlying_feature_matrix_interpretable
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S7.M03 — `diversity_redundancy_analyzer`
Medir redundância linear, ordinal, não linear, por regime, fonte e padrão de erro sem usar targets.
- Entradas: underlying_feature_matrix_interpretable
- Saídas: feature_diversity_redundancy_report
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S7.M04 — `structural_feature_selector`
Selecionar features por cobertura, estabilidade, lineage, missingness, custo e redundância estrutural.
- Entradas: underlying_feature_matrix_interpretable, feature_diversity_redundancy_report
- Saídas: underlying_feature_matrix_selected, feature_selection_report
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S8 — Representações cross-fitted

### P4.S8.M01 — `representation_fold_hyperparameter_controller`
Construir folds cronológicos cross-fitted, orçamento pequeno e pré-registrado de hiperparâmetros e plano de treinamento sem acesso a targets futuros.
- Entradas: underlying_feature_matrix_selected, horizon_feature_set_manifest, feature_transform_state_manifest
- Saídas: representation_fold_plan, encoder_hyperparameter_search_plan
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S8.M02 — `family_pca_sparse_pca_builder`
Construir PCA e Sparse PCA por família e horizonte, com fit cross-fitted, loadings, explained variance, estabilidade e lineage.
- Entradas: underlying_feature_matrix_selected, feature_transform_state_manifest, representation_fold_plan
- Saídas: underlying_feature_factors_pca, pca_fit_state_manifest
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S8.M03 — `family_shared_private_denoising_encoder_builder`
Construir somente o challenger de encoder raso por família, denoising/masked e shared-private, preservando modalidades e sem objetivo preditivo.
- Entradas: underlying_feature_matrix_selected, horizon_feature_set_manifest, feature_transform_state_manifest, representation_fold_plan, encoder_hyperparameter_search_plan
- Saídas: underlying_feature_embeddings, encoder_fit_state_manifest
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S8.M04 — `representation_quality_horizon_packager`
Avaliar estabilidade, reconstrução, degeneração, robustez, preservação de perspectivas e resultados da busca pequena; empacotar representações por horizonte.
- Entradas: underlying_feature_factors_pca, underlying_feature_embeddings, pca_fit_state_manifest, encoder_fit_state_manifest, representation_fold_plan
- Saídas: representation_quality_report, representation_horizon_bundle, encoder_hyperparameter_search_report
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

## P4.S9 — Garantia, ledger de pesquisa e handoff

### P4.S9.M01 — `feature_lineage_temporal_safety_auditor`
Reconstruir source→operator→fit→feature→representation e auditar segurança temporal ponta a ponta.
- Entradas: p4_output_candidate_bundle, all_fit_state_manifests
- Saídas: feature_lineage_report, temporal_safety_report
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S9.M02 — `drift_coverage_quality_gate`
Medir drift de dados, cobertura, missingness, dependências e latents; não medir concept drift supervisionado.
- Entradas: p4_output_candidate_bundle, feature_lineage_report, representation_quality_report
- Saídas: drift_safety_report, p4_quality_gate_decision
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S9.M03 — `model_consumer_view_packager`
Empacotar as mesmas informações em views tipadas para modelos tabulares, cross-sectionais, sequenciais, de grafo, cauda, regime, sparse e latentes sem escolher o modelo preditivo.
- Entradas: underlying_feature_matrix_raw, underlying_feature_matrix_selected, underlying_feature_factors_pca, underlying_feature_embeddings, horizon_feature_set_manifest, representation_quality_report, perspective_conflict_panel
- Saídas: model_consumer_view_manifest, model_consumer_view_bundle
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S9.M04 — `phase5_feature_handoff_builder`
Construir manifesto P4→P5 com outputs legados, views por consumidor, hashes, schemas, qualidade, fit states e limitações.
- Entradas: p4_output_candidate_bundle, feature_lineage_report, drift_safety_report, p4_quality_gate_decision, model_consumer_view_manifest
- Saídas: phase5_feature_handoff_manifest
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S9.M05 — `phase5_consumer_receipt_validator`
Validar o recibo da P5 e fechar a integração sem transformar consumo em qualificação econômica da P4.
- Entradas: phase5_feature_handoff_manifest, phase5_consumption_receipt
- Saídas: p4_to_p5_integration_receipt
- Status: `DOCUMENTED_NOT_IMPLEMENTED`

### P4.S9.M06 — `research_attempt_ledger_publisher`
Publicar ledger imutável de todas as tentativas, resultados negativos e rejeições, sem apagar graus de liberdade de pesquisa.
- Entradas: approved_hypothesis_passport_registry, hypothesis_budget_report, feature_selection_report, encoder_hyperparameter_search_report, representation_quality_report, drift_safety_report, phase5_feature_handoff_manifest
- Saídas: p4_research_attempt_ledger, p4_rejected_feature_graveyard, p4_research_governance_report
- Status: `DOCUMENTED_NOT_IMPLEMENTED`
