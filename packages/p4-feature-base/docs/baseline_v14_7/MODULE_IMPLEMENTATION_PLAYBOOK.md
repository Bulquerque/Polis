# Playbook de implementação módulo a módulo

Cada módulo deve ser implementado contra seu YAML, com testes antes de integração.

## P4.S1 — Autoridade de fronteira

### P4.S1.M01 — `phase2_handoff_validator`
**Responsabilidade:** Validar o bundle P2→P4, seus manifests, hashes, versões, grains, cobertura e temporalidade declarada.
**Dependências:** p2_required_bundle, p2_extension_bundle
**Entrega:** validated_phase2_bundle
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S1_M01_phase2_handoff_validator.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S1.M02 — `phase3_handoff_validator`
**Responsabilidade:** Validar o bundle interpretativo P3→P4 sem achatar evidência, disagreement, memória e hipóteses.
**Dependências:** p3_required_bundle
**Entrega:** validated_phase3_bundle
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S1_M02_phase3_handoff_validator.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S1.M03 — `boundary_consistency_gate`
**Responsabilidade:** Fechar run_id, cycle_id, universe_id, as_of_time, versões e consistência cruzada dos handoffs P2 e P3.
**Dependências:** validated_phase2_bundle, validated_phase3_bundle
**Entrega:** validated_p4_boundary_bundle
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S1_M03_boundary_consistency_gate.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S1.M04 — `n_plus_1_variable_evolution_intake`
**Responsabilidade:** Admitir propostas de evolução de variáveis apenas no ciclo N+1, sem otimizar features nem promover mudanças automaticamente.
**Dependências:** variable_evolution_input_manifest_optional, validated_p4_boundary_bundle
**Entrega:** observer_change_proposal_registry
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S1_M04_n_plus_1_variable_evolution_intake.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S2 — Autoridade temporal e painel canônico

### P4.S2.M01 — `temporal_semantics_resolver`
**Responsabilidade:** Resolver event_time, reference_time, published_at, available_at, ingested_at, decision_time e calculation_time.
**Dependências:** validated_p4_boundary_bundle
**Entrega:** temporally_resolved_observation_bundle
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S2_M01_temporal_semantics_resolver.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S2.M02 — `entity_calendar_corporate_action_aligner`
**Responsabilidade:** Harmonizar entity_id, underlying, venue, moeda, timezone, sessões, calendários e corporate actions.
**Dependências:** temporally_resolved_observation_bundle
**Entrega:** entity_aligned_observation_bundle
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S2_M02_entity_calendar_corporate_action_aligner.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S2.M03 — `revision_freshness_missingness_mapper`
**Responsabilidade:** Classificar vintage, revisão, staleness, cobertura, ausência estrutural, atraso e falha de fonte sem converter missing em zero.
**Dependências:** entity_aligned_observation_bundle
**Entrega:** availability_missingness_panel, quality_enriched_observation_bundle
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S2_M03_revision_freshness_missingness_mapper.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S2.M04 — `canonical_observation_store_builder`
**Responsabilidade:** Construir painel longo canônico e point-in-time para todos os cálculos posteriores.
**Dependências:** quality_enriched_observation_bundle, availability_missingness_panel
**Entrega:** canonical_observation_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S2_M04_canonical_observation_store_builder.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S3 — Governança de hipóteses, observadores e operadores

### P4.S3.M01 — `phenomenon_perspective_registry`
**Responsabilidade:** Registrar fenômenos, perspectivas, modalidades, mecanismos, horizontes, falhas conhecidas e regimes esperados.
**Dependências:** observer_change_proposal_registry
**Entrega:** feature_observer_registry, feature_parameter_policy_registry
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S3_M01_phenomenon_perspective_registry.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S3.M02 — `observer_spec_validator`
**Responsabilidade:** Validar receitas declarativas de observadores, dependências, janelas, lags, grains e políticas de disponibilidade.
**Dependências:** feature_observer_registry, canonical_observation_panel
**Entrega:** validated_observer_spec_registry
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S3_M02_observer_spec_validator.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S3.M03 — `causal_operator_engine`
**Responsabilidade:** Executar operadores temporais univariados causais e reproduzíveis com estados de fit versionados.
**Dependências:** validated_observer_spec_registry, canonical_observation_panel
**Entrega:** causal_operator_result_panel, operator_fit_state_registry
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S3_M03_causal_operator_engine.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S3.M04 — `relational_stateful_operator_engine`
**Responsabilidade:** Executar beta, correlação, residual, spread, lead-lag, cluster distance e agregações de grafo sem leakage.
**Dependências:** validated_observer_spec_registry, canonical_observation_panel
**Entrega:** relational_operator_result_panel, relational_fit_state_registry
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S3_M04_relational_stateful_operator_engine.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S3.M05 — `hypothesis_passport_budget_gate`
**Responsabilidade:** Validar passaportes teóricos, classificar hipóteses por tier e aplicar orçamento hierárquico antes de qualquer cálculo confirmatório.
**Dependências:** feature_observer_registry, feature_parameter_policy_registry, observer_change_proposal_registry, foundational_hypothesis_core_registry
**Entrega:** approved_hypothesis_passport_registry, hypothesis_budget_report, rejected_hypothesis_registry
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S3_M05_hypothesis_passport_budget_gate.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S4 — Fábricas de observações atômicas

### P4.S4.M01 — `price_return_observations`
**Responsabilidade:** Produzir retornos, gaps, ranges, posição no range, overnight/sessão e observações de preço ajustado.
**Dependências:** canonical_observation_panel, causal_operator_result_panel
**Entrega:** price_return_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M01_price_return_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S4.M02 — `volume_liquidity_microstructure_observations`
**Responsabilidade:** Produzir turnover, volume relativo, volume financeiro, Amihud, spread, staleness e impacto aproximado.
**Dependências:** canonical_observation_panel, causal_operator_result_panel
**Entrega:** liquidity_microstructure_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M02_volume_liquidity_microstructure_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S4.M03 — `realized_risk_tail_observations`
**Responsabilidade:** Produzir volatilidade realizada, semivariância, drawdown, skew, kurtosis, jumps e vol-of-vol.
**Dependências:** canonical_observation_panel, causal_operator_result_panel
**Entrega:** risk_tail_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M03_realized_risk_tail_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S4.M04 — `benchmark_cross_asset_observations`
**Responsabilidade:** Produzir retornos relativos, beta histórico, spreads, breadth, dispersão e dependências cross-asset.
**Dependências:** canonical_observation_panel, relational_operator_result_panel
**Entrega:** benchmark_cross_asset_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M04_benchmark_cross_asset_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S4.M05 — `underlying_option_state_observations`
**Responsabilidade:** Agregar option chain ao nível do underlying: IV ATM, skew, smile, term structure, IV-RV, OI e cobertura.
**Dependências:** canonical_observation_panel, relational_operator_result_panel
**Entrega:** underlying_option_state_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M05_underlying_option_state_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S4.M06 — `macro_event_calendar_observations`
**Responsabilidade:** Produzir mudanças macro, vintages, surpresas quando expectativa autorizada existir, curvas, eventos e sazonalidade.
**Dependências:** canonical_observation_panel, causal_operator_result_panel
**Entrega:** macro_event_calendar_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M06_macro_event_calendar_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S4.M07 — `social_evidence_context_observations`
**Responsabilidade:** Preservar direção, força, credibilidade, novidade, disagreement, memória, hipóteses e estabilidade narrativa.
**Dependências:** canonical_observation_panel, validated_phase3_bundle
**Entrega:** social_evidence_context_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M07_social_evidence_context_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S4.M08 — `fundamental_accounting_quality_observations`
**Responsabilidade:** Produzir observações point-in-time de valuation, rentabilidade, qualidade, investimento, alavancagem, accruals e evolução contábil, com vintages e disponibilidade explícitos.
**Dependências:** canonical_observation_panel, causal_operator_result_panel, validated_phase2_bundle
**Entrega:** fundamental_accounting_atomic_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S4_M08_fundamental_accounting_quality_observations.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S5 — Fábricas de perspectivas econômicas

### P4.S5.M01 — `momentum_trend_persistence_perspectives`
**Responsabilidade:** Construir views de momentum por retorno, slope, breakout, persistência, residual, volume, opções, narrativa e P3.
**Dependências:** atomic_observation_bundle
**Entrega:** momentum_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M01_momentum_trend_persistence_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M02 — `reversion_relative_value_perspectives`
**Responsabilidade:** Construir views de reversão por média, residual, pares, setor, cluster, gap, volume e saturação narrativa.
**Dependências:** atomic_observation_bundle
**Entrega:** reversion_relative_value_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M02_reversion_relative_value_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M03 — `risk_uncertainty_stress_perspectives`
**Responsabilidade:** Construir views de risco realizado, implícito, downside, cauda, instabilidade, surpresa e disagreement.
**Dependências:** atomic_observation_bundle
**Entrega:** risk_uncertainty_stress_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M03_risk_uncertainty_stress_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M04 — `liquidity_attention_crowding_perspectives`
**Responsabilidade:** Construir views de iliquidez, atenção, concentração, OI, consenso excessivo e crowding.
**Dependências:** atomic_observation_bundle
**Entrega:** liquidity_attention_crowding_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M04_liquidity_attention_crowding_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M05 — `structure_contagion_breadth_perspectives`
**Responsabilidade:** Construir views de market mode, effective rank, eigen entropy, centralidade, propagação, dispersão e breadth.
**Dependências:** atomic_observation_bundle
**Entrega:** structure_contagion_breadth_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M05_structure_contagion_breadth_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M06 — `macro_cycle_regime_state_perspectives`
**Responsabilidade:** Descrever estado contemporâneo de inflação, crescimento, liquidez, curva, stress e distância histórica.
**Dependências:** atomic_observation_bundle
**Entrega:** macro_cycle_regime_state_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M06_macro_cycle_regime_state_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M07 — `event_surprise_seasonality_perspectives`
**Responsabilidade:** Construir views de tempo até/des­de evento, reação contemporânea, persistência, reversão e sazonalidade.
**Dependências:** atomic_observation_bundle
**Entrega:** event_surprise_seasonality_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M07_event_surprise_seasonality_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M08 — `narrative_evidence_disagreement_perspectives`
**Responsabilidade:** Construir views de consenso, polarização, contradição, novidade, diversidade de hipóteses e visão minoritária.
**Dependências:** atomic_observation_bundle
**Entrega:** narrative_evidence_disagreement_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M08_narrative_evidence_disagreement_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M09 — `value_quality_profitability_investment_perspectives`
**Responsabilidade:** Construir perspectivas de value, qualidade, profitability, investment, leverage e accruals sem usar retornos futuros para selecionar ou calibrar sinais.
**Dependências:** atomic_observation_bundle
**Entrega:** value_quality_profitability_investment_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M09_value_quality_profitability_investment_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S5.M10 — `carry_curve_basis_perspectives`
**Responsabilidade:** Construir perspectivas de carry, roll-down, basis, inclinação e curvatura de estruturas a termo em classes de ativos para as quais os dados existam.
**Dependências:** atomic_observation_bundle
**Entrega:** carry_curve_basis_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S5_M10_carry_curve_basis_perspectives.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S6 — Fusão, confirmação, conflito e horizontes

### P4.S6.M01 — `multi_view_alignment`
**Responsabilidade:** Alinhar perspectivas por entidade, fenômeno, decision_time e horizonte mantendo views ausentes explicitamente.
**Dependências:** perspective_family_bundle
**Entrega:** aligned_perspective_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S6_M01_multi_view_alignment.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S6.M02 — `confirmation_conflict_engine`
**Responsabilidade:** Medir consenso, dispersão, entropia, confirmação independente, conflito modal e força de visão minoritária.
**Dependências:** aligned_perspective_panel
**Entrega:** perspective_conflict_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S6_M02_confirmation_conflict_engine.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S6.M03 — `hypothesis_constrained_interaction_builder`
**Responsabilidade:** Criar apenas interações registradas com racional econômico, famílias de origem e risco de overfitting.
**Dependências:** aligned_perspective_panel, feature_observer_registry
**Entrega:** interaction_feature_panel
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S6_M03_hypothesis_constrained_interaction_builder.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S6.M04 — `multi_horizon_missing_view_assembler`
**Responsabilidade:** Organizar views e conflitos em conjuntos intraday, short, medium, long e cross-horizon.
**Dependências:** aligned_perspective_panel, perspective_conflict_panel, interaction_feature_panel, availability_missingness_panel
**Entrega:** horizon_feature_panel, horizon_feature_set_manifest
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S6_M04_multi_horizon_missing_view_assembler.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S7 — Transformação causal e seleção estrutural

### P4.S7.M01 — `causal_transform_fit_engine`
**Responsabilidade:** Aplicar winsorization, log, clipping e scalers com fit_start, fit_end e estado versionado.
**Dependências:** horizon_feature_panel
**Entrega:** causally_transformed_feature_panel, feature_transform_state_manifest
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S7_M01_causal_transform_fit_engine.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S7.M02 — `normalization_neutralization_engine`
**Responsabilidade:** Produzir versões rank/z-score e neutralizações por mercado, setor, beta, volatilidade, tamanho e moeda.
**Dependências:** causally_transformed_feature_panel
**Entrega:** underlying_feature_matrix_interpretable
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S7_M02_normalization_neutralization_engine.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S7.M03 — `diversity_redundancy_analyzer`
**Responsabilidade:** Medir redundância linear, ordinal, não linear, por regime, fonte e padrão de erro sem usar targets.
**Dependências:** underlying_feature_matrix_interpretable
**Entrega:** feature_diversity_redundancy_report
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S7_M03_diversity_redundancy_analyzer.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S7.M04 — `structural_feature_selector`
**Responsabilidade:** Selecionar features por cobertura, estabilidade, lineage, missingness, custo e redundância estrutural.
**Dependências:** underlying_feature_matrix_interpretable, feature_diversity_redundancy_report
**Entrega:** underlying_feature_matrix_selected, feature_selection_report
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S7_M04_structural_feature_selector.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S8 — Representações cross-fitted

### P4.S8.M01 — `representation_fold_hyperparameter_controller`
**Responsabilidade:** Construir folds cronológicos cross-fitted, orçamento pequeno e pré-registrado de hiperparâmetros e plano de treinamento sem acesso a targets futuros.
**Dependências:** underlying_feature_matrix_selected, horizon_feature_set_manifest, feature_transform_state_manifest
**Entrega:** representation_fold_plan, encoder_hyperparameter_search_plan
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S8_M01_representation_fold_hyperparameter_controller.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S8.M02 — `family_pca_sparse_pca_builder`
**Responsabilidade:** Construir PCA e Sparse PCA por família e horizonte, com fit cross-fitted, loadings, explained variance, estabilidade e lineage.
**Dependências:** underlying_feature_matrix_selected, feature_transform_state_manifest, representation_fold_plan
**Entrega:** underlying_feature_factors_pca, pca_fit_state_manifest
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S8_M02_family_pca_sparse_pca_builder.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S8.M03 — `family_shared_private_denoising_encoder_builder`
**Responsabilidade:** Construir somente o challenger de encoder raso por família, denoising/masked e shared-private, preservando modalidades e sem objetivo preditivo.
**Dependências:** underlying_feature_matrix_selected, horizon_feature_set_manifest, feature_transform_state_manifest, representation_fold_plan, encoder_hyperparameter_search_plan
**Entrega:** underlying_feature_embeddings, encoder_fit_state_manifest
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S8_M03_family_shared_private_denoising_encoder_builder.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S8.M04 — `representation_quality_horizon_packager`
**Responsabilidade:** Avaliar estabilidade, reconstrução, degeneração, robustez, preservação de perspectivas e resultados da busca pequena; empacotar representações por horizonte.
**Dependências:** underlying_feature_factors_pca, underlying_feature_embeddings, pca_fit_state_manifest, encoder_fit_state_manifest, representation_fold_plan
**Entrega:** representation_quality_report, representation_horizon_bundle, encoder_hyperparameter_search_report
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S8_M04_representation_quality_horizon_packager.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

## P4.S9 — Garantia, ledger de pesquisa e handoff

### P4.S9.M01 — `feature_lineage_temporal_safety_auditor`
**Responsabilidade:** Reconstruir source→operator→fit→feature→representation e auditar segurança temporal ponta a ponta.
**Dependências:** p4_output_candidate_bundle, all_fit_state_manifests
**Entrega:** feature_lineage_report, temporal_safety_report
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S9_M01_feature_lineage_temporal_safety_auditor.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S9.M02 — `drift_coverage_quality_gate`
**Responsabilidade:** Medir drift de dados, cobertura, missingness, dependências e latents; não medir concept drift supervisionado.
**Dependências:** p4_output_candidate_bundle, feature_lineage_report, representation_quality_report
**Entrega:** drift_safety_report, p4_quality_gate_decision
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S9_M02_drift_coverage_quality_gate.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S9.M03 — `model_consumer_view_packager`
**Responsabilidade:** Empacotar as mesmas informações em views tipadas para modelos tabulares, cross-sectionais, sequenciais, de grafo, cauda, regime, sparse e latentes sem escolher o modelo preditivo.
**Dependências:** underlying_feature_matrix_raw, underlying_feature_matrix_selected, underlying_feature_factors_pca, underlying_feature_embeddings, horizon_feature_set_manifest, representation_quality_report, perspective_conflict_panel
**Entrega:** model_consumer_view_manifest, model_consumer_view_bundle
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S9_M03_model_consumer_view_packager.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S9.M04 — `phase5_feature_handoff_builder`
**Responsabilidade:** Construir manifesto P4→P5 com outputs legados, views por consumidor, hashes, schemas, qualidade, fit states e limitações.
**Dependências:** p4_output_candidate_bundle, feature_lineage_report, drift_safety_report, p4_quality_gate_decision, model_consumer_view_manifest
**Entrega:** phase5_feature_handoff_manifest
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S9_M04_phase5_feature_handoff_builder.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S9.M05 — `phase5_consumer_receipt_validator`
**Responsabilidade:** Validar o recibo da P5 e fechar a integração sem transformar consumo em qualificação econômica da P4.
**Dependências:** phase5_feature_handoff_manifest, phase5_consumption_receipt
**Entrega:** p4_to_p5_integration_receipt
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S9_M05_phase5_consumer_receipt_validator.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.

### P4.S9.M06 — `research_attempt_ledger_publisher`
**Responsabilidade:** Publicar ledger imutável de todas as tentativas, resultados negativos e rejeições, sem apagar graus de liberdade de pesquisa.
**Dependências:** approved_hypothesis_passport_registry, hypothesis_budget_report, feature_selection_report, encoder_hyperparameter_search_report, representation_quality_report, drift_safety_report, phase5_feature_handoff_manifest
**Entrega:** p4_research_attempt_ledger, p4_rejected_feature_graveyard, p4_research_governance_report
**Implementação alvo:** `src/quant_pipeline/phase_04_feature_base/modules/P4_S9_M06_research_attempt_ledger_publisher.py`
**Testes mínimos:** schema, tempo, campos proibidos, lineage, replay e oracle numérico/metamórfico quando aplicável.
**Gate:** não integrar antes de todos os fail-fast do contrato e da evidência de teste independente.
