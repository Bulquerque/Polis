# Blueprint detalhado módulo a módulo

Este documento é a especificação operacional de implementação. Contratos YAML continuam sendo a autoridade de máquina.

## P4.S1

Estabelecer autenticidade e coerência das fronteiras antes de qualquer transformação.

### P4.S1.M01 — `phase2_handoff_validator`

**Responsabilidade:** Validar o bundle P2→P4, seus manifests, hashes, versões, grains, cobertura e temporalidade declarada.

**Implementação técnica:** Validar manifesto, hashes, schema versions, contagens, períodos, quality state e produtores da P2. Não aceitar artefatos vazios como presença válida.

**Entradas contratuais:** p2_required_bundle, p2_extension_bundle
**Saídas contratuais:** validated_phase2_bundle
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S1_M01_INPUT_INVALID, P4_S1_M01_TEMPORAL_VIOLATION, P4_S1_M01_OUTPUT_INVALID, P4_S1_M01_FORBIDDEN_FIELD, P4_S1_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S1.M02 — `phase3_handoff_validator`

**Responsabilidade:** Validar o bundle interpretativo P3→P4 sem achatar evidência, disagreement, memória e hipóteses.

**Implementação técnica:** Validar os seis artefatos P3→P4 e preservar evidence, disagreement, memory e hypotheses como modalidades separadas.

**Entradas contratuais:** p3_required_bundle
**Saídas contratuais:** validated_phase3_bundle
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S1_M02_INPUT_INVALID, P4_S1_M02_TEMPORAL_VIOLATION, P4_S1_M02_OUTPUT_INVALID, P4_S1_M02_FORBIDDEN_FIELD, P4_S1_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S1.M03 — `boundary_consistency_gate`

**Responsabilidade:** Fechar run_id, cycle_id, universe_id, as_of_time, versões e consistência cruzada dos handoffs P2 e P3.

**Implementação técnica:** Fechar run_id, cycle_id, universe_id, as_of_time e compatibilidade entre manifestos; qualquer divergência bloqueia antes do cálculo.

**Entradas contratuais:** validated_phase2_bundle, validated_phase3_bundle
**Saídas contratuais:** validated_p4_boundary_bundle
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S1_M03_INPUT_INVALID, P4_S1_M03_TEMPORAL_VIOLATION, P4_S1_M03_OUTPUT_INVALID, P4_S1_M03_FORBIDDEN_FIELD, P4_S1_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S1.M04 — `n_plus_1_variable_evolution_intake`

**Responsabilidade:** Admitir propostas de evolução de variáveis apenas no ciclo N+1, sem otimizar features nem promover mudanças automaticamente.

**Implementação técnica:** Aceitar propostas de variável somente no ciclo N+1, com aprovação P0, passaporte e orçamento; nunca aceitar resultado do mesmo ciclo.

**Entradas contratuais:** variable_evolution_input_manifest_optional, validated_p4_boundary_bundle
**Saídas contratuais:** observer_change_proposal_registry
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S1_M04_INPUT_INVALID, P4_S1_M04_TEMPORAL_VIOLATION, P4_S1_M04_OUTPUT_INVALID, P4_S1_M04_FORBIDDEN_FIELD, P4_S1_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S2

Construir a autoridade bitemporal e semântica que impede leakage.

### P4.S2.M01 — `temporal_semantics_resolver`

**Responsabilidade:** Resolver event_time, reference_time, published_at, available_at, ingested_at, decision_time e calculation_time.

**Implementação técnica:** Canonicalizar event/reference/published/available/ingested/decision/calculation time e provar available_at <= decision_time.

**Entradas contratuais:** validated_p4_boundary_bundle
**Saídas contratuais:** temporally_resolved_observation_bundle
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S2_M01_INPUT_INVALID, P4_S2_M01_TEMPORAL_VIOLATION, P4_S2_M01_OUTPUT_INVALID, P4_S2_M01_FORBIDDEN_FIELD, P4_S2_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S2.M02 — `entity_calendar_corporate_action_aligner`

**Responsabilidade:** Harmonizar entity_id, underlying, venue, moeda, timezone, sessões, calendários e corporate actions.

**Implementação técnica:** Resolver IDs, venue, moeda, timezone, sessão, feriados e corporate actions sem alterar observações históricas já publicadas.

**Entradas contratuais:** temporally_resolved_observation_bundle
**Saídas contratuais:** entity_aligned_observation_bundle
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S2_M02_INPUT_INVALID, P4_S2_M02_TEMPORAL_VIOLATION, P4_S2_M02_OUTPUT_INVALID, P4_S2_M02_FORBIDDEN_FIELD, P4_S2_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S2.M03 — `revision_freshness_missingness_mapper`

**Responsabilidade:** Classificar vintage, revisão, staleness, cobertura, ausência estrutural, atraso e falha de fonte sem converter missing em zero.

**Implementação técnica:** Mapear vintage, revisão, freshness e estados de missingness; proibir default temporal e missing→zero.

**Entradas contratuais:** entity_aligned_observation_bundle
**Saídas contratuais:** availability_missingness_panel, quality_enriched_observation_bundle
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S2_M03_INPUT_INVALID, P4_S2_M03_TEMPORAL_VIOLATION, P4_S2_M03_OUTPUT_INVALID, P4_S2_M03_FORBIDDEN_FIELD, P4_S2_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S2.M04 — `canonical_observation_store_builder`

**Responsabilidade:** Construir painel longo canônico e point-in-time para todos os cálculos posteriores.

**Implementação técnica:** Construir painel longo por entity_id×variable_id×decision_time, com valor, máscara, qualidade e lineage. Não construir matriz wide prematuramente.

**Entradas contratuais:** quality_enriched_observation_bundle, availability_missingness_panel
**Saídas contratuais:** canonical_observation_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S2_M04_INPUT_INVALID, P4_S2_M04_TEMPORAL_VIOLATION, P4_S2_M04_OUTPUT_INVALID, P4_S2_M04_FORBIDDEN_FIELD, P4_S2_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S3

Governar a teoria, as receitas e o orçamento científico.

### P4.S3.M01 — `phenomenon_perspective_registry`

**Responsabilidade:** Registrar fenômenos, perspectivas, modalidades, mecanismos, horizontes, falhas conhecidas e regimes esperados.

**Implementação técnica:** Manter ontologia fenômeno→perspectiva→observador→parâmetro e evitar que fonte, técnica e fenômeno sejam misturados.

**Entradas contratuais:** observer_change_proposal_registry
**Saídas contratuais:** feature_observer_registry, feature_parameter_policy_registry
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S3_M01_INPUT_INVALID, P4_S3_M01_TEMPORAL_VIOLATION, P4_S3_M01_OUTPUT_INVALID, P4_S3_M01_FORBIDDEN_FIELD, P4_S3_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S3.M02 — `observer_spec_validator`

**Responsabilidade:** Validar receitas declarativas de observadores, dependências, janelas, lags, grains e políticas de disponibilidade.

**Implementação técnica:** Validar receita DSL, inputs, operadores, grain, lag, horizonte, racional, parâmetros e campos proibidos antes da execução.

**Entradas contratuais:** feature_observer_registry, canonical_observation_panel
**Saídas contratuais:** validated_observer_spec_registry
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S3_M02_INPUT_INVALID, P4_S3_M02_TEMPORAL_VIOLATION, P4_S3_M02_OUTPUT_INVALID, P4_S3_M02_FORBIDDEN_FIELD, P4_S3_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S3.M03 — `causal_operator_engine`

**Responsabilidade:** Executar operadores temporais univariados causais e reproduzíveis com estados de fit versionados.

**Implementação técnica:** Implementar operadores causais vetorizados com estados explícitos, min_periods, máscaras e oracles; nenhum operador pode consultar linhas futuras.

**Entradas contratuais:** validated_observer_spec_registry, canonical_observation_panel
**Saídas contratuais:** causal_operator_result_panel, operator_fit_state_registry
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S3_M03_INPUT_INVALID, P4_S3_M03_TEMPORAL_VIOLATION, P4_S3_M03_OUTPUT_INVALID, P4_S3_M03_FORBIDDEN_FIELD, P4_S3_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S3.M04 — `relational_stateful_operator_engine`

**Responsabilidade:** Executar beta, correlação, residual, spread, lead-lag, cluster distance e agregações de grafo sem leakage.

**Implementação técnica:** Implementar relações, regressões rolling, grafos e estados persistentes com universo e janela congelados por cutoff.

**Entradas contratuais:** validated_observer_spec_registry, canonical_observation_panel
**Saídas contratuais:** relational_operator_result_panel, relational_fit_state_registry
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S3_M04_INPUT_INVALID, P4_S3_M04_TEMPORAL_VIOLATION, P4_S3_M04_OUTPUT_INVALID, P4_S3_M04_FORBIDDEN_FIELD, P4_S3_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S3.M05 — `hypothesis_passport_budget_gate`

**Responsabilidade:** Validar passaportes teóricos, classificar hipóteses por tier e aplicar orçamento hierárquico antes de qualquer cálculo confirmatório.

**Implementação técnica:** Validar 32 passaportes, máximo de duas parametrizações, tier e ledger. Rejeitar tentativa não registrada.

**Entradas contratuais:** feature_observer_registry, feature_parameter_policy_registry, observer_change_proposal_registry, foundational_hypothesis_core_registry
**Saídas contratuais:** approved_hypothesis_passport_registry, hypothesis_budget_report, rejected_hypothesis_registry
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S3_M05_INPUT_INVALID, P4_S3_M05_TEMPORAL_VIOLATION, P4_S3_M05_OUTPUT_INVALID, P4_S3_M05_FORBIDDEN_FIELD, P4_S3_M05_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S4

Produzir observações atômicas reutilizáveis por modalidade.

### P4.S4.M01 — `price_return_observations`

**Responsabilidade:** Produzir retornos, gaps, ranges, posição no range, overnight/sessão e observações de preço ajustado.

**Implementação técnica:** Gerar preços ajustados, retornos, ranges, gaps e posição no range com tratamento correto de splits/dividendos.

**Entradas contratuais:** canonical_observation_panel, causal_operator_result_panel
**Saídas contratuais:** price_return_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M01_INPUT_INVALID, P4_S4_M01_TEMPORAL_VIOLATION, P4_S4_M01_OUTPUT_INVALID, P4_S4_M01_FORBIDDEN_FIELD, P4_S4_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S4.M02 — `volume_liquidity_microstructure_observations`

**Responsabilidade:** Produzir turnover, volume relativo, volume financeiro, Amihud, spread, staleness e impacto aproximado.

**Implementação técnica:** Gerar turnover, volume relativo, dollar volume, spreads/proxies, impacto e staleness sem confundir volume com liquidez.

**Entradas contratuais:** canonical_observation_panel, causal_operator_result_panel
**Saídas contratuais:** liquidity_microstructure_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M02_INPUT_INVALID, P4_S4_M02_TEMPORAL_VIOLATION, P4_S4_M02_OUTPUT_INVALID, P4_S4_M02_FORBIDDEN_FIELD, P4_S4_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S4.M03 — `realized_risk_tail_observations`

**Responsabilidade:** Produzir volatilidade realizada, semivariância, drawdown, skew, kurtosis, jumps e vol-of-vol.

**Implementação técnica:** Gerar realized variance, semivariância, drawdown, jumps e vol-of-vol por escalas pré-registradas.

**Entradas contratuais:** canonical_observation_panel, causal_operator_result_panel
**Saídas contratuais:** risk_tail_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M03_INPUT_INVALID, P4_S4_M03_TEMPORAL_VIOLATION, P4_S4_M03_OUTPUT_INVALID, P4_S4_M03_FORBIDDEN_FIELD, P4_S4_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S4.M04 — `benchmark_cross_asset_observations`

**Responsabilidade:** Produzir retornos relativos, beta histórico, spreads, breadth, dispersão e dependências cross-asset.

**Implementação técnica:** Gerar retornos relativos, beta, residual, breadth, dispersão e relações cross-asset com universo point-in-time.

**Entradas contratuais:** canonical_observation_panel, relational_operator_result_panel
**Saídas contratuais:** benchmark_cross_asset_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M04_INPUT_INVALID, P4_S4_M04_TEMPORAL_VIOLATION, P4_S4_M04_OUTPUT_INVALID, P4_S4_M04_FORBIDDEN_FIELD, P4_S4_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S4.M05 — `underlying_option_state_observations`

**Responsabilidade:** Agregar option chain ao nível do underlying: IV ATM, skew, smile, term structure, IV-RV, OI e cobertura.

**Implementação técnica:** Agregar option chain ao underlying: IV ATM, skew, term structure, VRP, OI/volume e cobertura; não criar pernas ou candidatos.

**Entradas contratuais:** canonical_observation_panel, relational_operator_result_panel
**Saídas contratuais:** underlying_option_state_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M05_INPUT_INVALID, P4_S4_M05_TEMPORAL_VIOLATION, P4_S4_M05_OUTPUT_INVALID, P4_S4_M05_FORBIDDEN_FIELD, P4_S4_M05_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S4.M06 — `macro_event_calendar_observations`

**Responsabilidade:** Produzir mudanças macro, vintages, surpresas quando expectativa autorizada existir, curvas, eventos e sazonalidade.

**Implementação técnica:** Gerar vintages macro, surpresas, curvas, calendário e tempos de evento; expectativa ausente permanece missing.

**Entradas contratuais:** canonical_observation_panel, causal_operator_result_panel
**Saídas contratuais:** macro_event_calendar_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M06_INPUT_INVALID, P4_S4_M06_TEMPORAL_VIOLATION, P4_S4_M06_OUTPUT_INVALID, P4_S4_M06_FORBIDDEN_FIELD, P4_S4_M06_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S4.M07 — `social_evidence_context_observations`

**Responsabilidade:** Preservar direção, força, credibilidade, novidade, disagreement, memória, hipóteses e estabilidade narrativa.

**Implementação técnica:** Projetar P3 em direção, novidade, credibilidade, disagreement, memória e hipóteses separadas, com masks por modalidade.

**Entradas contratuais:** canonical_observation_panel, validated_phase3_bundle
**Saídas contratuais:** social_evidence_context_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M07_INPUT_INVALID, P4_S4_M07_TEMPORAL_VIOLATION, P4_S4_M07_OUTPUT_INVALID, P4_S4_M07_FORBIDDEN_FIELD, P4_S4_M07_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S4.M08 — `fundamental_accounting_quality_observations`

**Responsabilidade:** Produzir observações point-in-time de valuation, rentabilidade, qualidade, investimento, alavancagem, accruals e evolução contábil, com vintages e disponibilidade explícitos.

**Implementação técnica:** Gerar fundamentais PIT com data real de filing, fiscal period, restatement e lag; nunca usar snapshot Compustat revisado como histórico original.

**Entradas contratuais:** canonical_observation_panel, causal_operator_result_panel, validated_phase2_bundle
**Saídas contratuais:** fundamental_accounting_atomic_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S4_M08_INPUT_INVALID, P4_S4_M08_TEMPORAL_VIOLATION, P4_S4_M08_OUTPUT_INVALID, P4_S4_M08_FORBIDDEN_FIELD, P4_S4_M08_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S5

Transformar observações em perspectivas economicamente distintas.

### P4.S5.M01 — `momentum_trend_persistence_perspectives`

**Responsabilidade:** Construir views de momentum por retorno, slope, breakout, persistência, residual, volume, opções, narrativa e P3.

**Implementação técnica:** Construir apenas as quatro hipóteses fundamentais de momentum e extensões registradas; janelas vizinhas não viram novas teorias.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** momentum_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M01_INPUT_INVALID, P4_S5_M01_TEMPORAL_VIOLATION, P4_S5_M01_OUTPUT_INVALID, P4_S5_M01_FORBIDDEN_FIELD, P4_S5_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M02 — `reversion_relative_value_perspectives`

**Responsabilidade:** Construir views de reversão por média, residual, pares, setor, cluster, gap, volume e saturação narrativa.

**Implementação técnica:** Separar pressão temporária, desvio robusto e reversão residual; pairs/cluster ficam extension-tier.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** reversion_relative_value_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M02_INPUT_INVALID, P4_S5_M02_TEMPORAL_VIOLATION, P4_S5_M02_OUTPUT_INVALID, P4_S5_M02_FORBIDDEN_FIELD, P4_S5_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M03 — `risk_uncertainty_stress_perspectives`

**Responsabilidade:** Construir views de risco realizado, implícito, downside, cauda, instabilidade, surpresa e disagreement.

**Implementação técnica:** Combinar estado multiescala, downside, drawdown e risco implícito sem resumir tudo em uma volatilidade única.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** risk_uncertainty_stress_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M03_INPUT_INVALID, P4_S5_M03_TEMPORAL_VIOLATION, P4_S5_M03_OUTPUT_INVALID, P4_S5_M03_FORBIDDEN_FIELD, P4_S5_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M04 — `liquidity_attention_crowding_perspectives`

**Responsabilidade:** Construir views de iliquidez, atenção, concentração, OI, consenso excessivo e crowding.

**Implementação técnica:** Construir liquidez, atenção e crowding como perspectivas distintas; registrar capacidade e custo como dependência downstream.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** liquidity_attention_crowding_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M04_INPUT_INVALID, P4_S5_M04_TEMPORAL_VIOLATION, P4_S5_M04_OUTPUT_INVALID, P4_S5_M04_FORBIDDEN_FIELD, P4_S5_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M05 — `structure_contagion_breadth_perspectives`

**Responsabilidade:** Construir views de market mode, effective rank, eigen entropy, centralidade, propagação, dispersão e breadth.

**Implementação técnica:** Preservar direção de transmissão, concentração do modo comum, breadth e horizontes de connectedness.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** structure_contagion_breadth_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M05_INPUT_INVALID, P4_S5_M05_TEMPORAL_VIOLATION, P4_S5_M05_OUTPUT_INVALID, P4_S5_M05_FORBIDDEN_FIELD, P4_S5_M05_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M06 — `macro_cycle_regime_state_perspectives`

**Responsabilidade:** Descrever estado contemporâneo de inflação, crescimento, liquidez, curva, stress e distância histórica.

**Implementação técnica:** Descrever estado macro contemporâneo, não prever retorno; usar vintages e estados conjuntos crescimento×inflação×condições financeiras.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** macro_cycle_regime_state_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M06_INPUT_INVALID, P4_S5_M06_TEMPORAL_VIOLATION, P4_S5_M06_OUTPUT_INVALID, P4_S5_M06_FORBIDDEN_FIELD, P4_S5_M06_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M07 — `event_surprise_seasonality_perspectives`

**Responsabilidade:** Construir views de tempo até/des­de evento, reação contemporânea, persistência, reversão e sazonalidade.

**Implementação técnica:** Separar surpresa, reação inicial, tempo desde evento, drift e sazonalidade; impedir sobreposição de eventos não tratada.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** event_surprise_seasonality_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M07_INPUT_INVALID, P4_S5_M07_TEMPORAL_VIOLATION, P4_S5_M07_OUTPUT_INVALID, P4_S5_M07_FORBIDDEN_FIELD, P4_S5_M07_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M08 — `narrative_evidence_disagreement_perspectives`

**Responsabilidade:** Construir views de consenso, polarização, contradição, novidade, diversidade de hipóteses e visão minoritária.

**Implementação técnica:** Preservar novidade, disagreement e mudança narrativa; credibilidade funciona como dimensão/peso, não label de retorno.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** narrative_evidence_disagreement_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M08_INPUT_INVALID, P4_S5_M08_TEMPORAL_VIOLATION, P4_S5_M08_OUTPUT_INVALID, P4_S5_M08_FORBIDDEN_FIELD, P4_S5_M08_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M09 — `value_quality_profitability_investment_perspectives`

**Responsabilidade:** Construir perspectivas de value, qualidade, profitability, investment, leverage e accruals sem usar retornos futuros para selecionar ou calibrar sinais.

**Implementação técnica:** Implementar value, profitability, investment e accrual quality com uma definição primária e uma robustez.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** value_quality_profitability_investment_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M09_INPUT_INVALID, P4_S5_M09_TEMPORAL_VIOLATION, P4_S5_M09_OUTPUT_INVALID, P4_S5_M09_FORBIDDEN_FIELD, P4_S5_M09_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S5.M10 — `carry_curve_basis_perspectives`

**Responsabilidade:** Construir perspectivas de carry, roll-down, basis, inclinação e curvatura de estruturas a termo em classes de ativos para as quais os dados existam.

**Implementação técnica:** Implementar carry/basis/roll-down por classe com convenções explícitas, calendários e maturidades comparáveis.

**Entradas contratuais:** atomic_observation_bundle
**Saídas contratuais:** carry_curve_basis_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S5_M10_INPUT_INVALID, P4_S5_M10_TEMPORAL_VIOLATION, P4_S5_M10_OUTPUT_INVALID, P4_S5_M10_FORBIDDEN_FIELD, P4_S5_M10_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S6

Relacionar perspectivas, preservar conflito e organizar horizontes.

### P4.S6.M01 — `multi_view_alignment`

**Responsabilidade:** Alinhar perspectivas por entidade, fenômeno, decision_time e horizonte mantendo views ausentes explicitamente.

**Implementação técnica:** Alinhar views sem imputação silenciosa; produzir máscaras, idade da informação e conjunto de modalidades presentes.

**Entradas contratuais:** perspective_family_bundle
**Saídas contratuais:** aligned_perspective_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S6_M01_INPUT_INVALID, P4_S6_M01_TEMPORAL_VIOLATION, P4_S6_M01_OUTPUT_INVALID, P4_S6_M01_FORBIDDEN_FIELD, P4_S6_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S6.M02 — `confirmation_conflict_engine`

**Responsabilidade:** Medir consenso, dispersão, entropia, confirmação independente, conflito modal e força de visão minoritária.

**Implementação técnica:** Medir consenso, entropia, conflito de sinal, confirmação independente e visão minoritária sem usar labels.

**Entradas contratuais:** aligned_perspective_panel
**Saídas contratuais:** perspective_conflict_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S6_M02_INPUT_INVALID, P4_S6_M02_TEMPORAL_VIOLATION, P4_S6_M02_OUTPUT_INVALID, P4_S6_M02_FORBIDDEN_FIELD, P4_S6_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S6.M03 — `hypothesis_constrained_interaction_builder`

**Responsabilidade:** Criar apenas interações registradas com racional econômico, famílias de origem e risco de overfitting.

**Implementação técnica:** Materializar somente interações aprovadas no registry; cada interação possui hipótese, pais, dimensionalidade e custo.

**Entradas contratuais:** aligned_perspective_panel, feature_observer_registry
**Saídas contratuais:** interaction_feature_panel
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S6_M03_INPUT_INVALID, P4_S6_M03_TEMPORAL_VIOLATION, P4_S6_M03_OUTPUT_INVALID, P4_S6_M03_FORBIDDEN_FIELD, P4_S6_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S6.M04 — `multi_horizon_missing_view_assembler`

**Responsabilidade:** Organizar views e conflitos em conjuntos intraday, short, medium, long e cross-horizon.

**Implementação técnica:** Empacotar short/medium/long e cross-horizon preservando masks e evitando duplicação da mesma hipótese em múltiplas janelas.

**Entradas contratuais:** aligned_perspective_panel, perspective_conflict_panel, interaction_feature_panel, availability_missingness_panel
**Saídas contratuais:** horizon_feature_panel, horizon_feature_set_manifest
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S6_M04_INPUT_INVALID, P4_S6_M04_TEMPORAL_VIOLATION, P4_S6_M04_OUTPUT_INVALID, P4_S6_M04_FORBIDDEN_FIELD, P4_S6_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S7

Transformar causalmente e reduzir redundância sem labels.

### P4.S7.M01 — `causal_transform_fit_engine`

**Responsabilidade:** Aplicar winsorization, log, clipping e scalers com fit_start, fit_end e estado versionado.

**Implementação técnica:** Fit causal de scalers/winsorization; estados imutáveis e aplicados somente após fit_end.

**Entradas contratuais:** horizon_feature_panel
**Saídas contratuais:** causally_transformed_feature_panel, feature_transform_state_manifest
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S7_M01_INPUT_INVALID, P4_S7_M01_TEMPORAL_VIOLATION, P4_S7_M01_OUTPUT_INVALID, P4_S7_M01_FORBIDDEN_FIELD, P4_S7_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S7.M02 — `normalization_neutralization_engine`

**Responsabilidade:** Produzir versões rank/z-score e neutralizações por mercado, setor, beta, volatilidade, tamanho e moeda.

**Implementação técnica:** Produzir raw, rank e neutralized side by side; neutralização nunca sobrescreve a versão original.

**Entradas contratuais:** causally_transformed_feature_panel
**Saídas contratuais:** underlying_feature_matrix_interpretable
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S7_M02_INPUT_INVALID, P4_S7_M02_TEMPORAL_VIOLATION, P4_S7_M02_OUTPUT_INVALID, P4_S7_M02_FORBIDDEN_FIELD, P4_S7_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S7.M03 — `diversity_redundancy_analyzer`

**Responsabilidade:** Medir redundância linear, ordinal, não linear, por regime, fonte e padrão de erro sem usar targets.

**Implementação técnica:** Medir correlação, rank, mutual information e redundância em grupos; proxies correlacionados devem ser tratados como cluster, não eliminados cegamente.

**Entradas contratuais:** underlying_feature_matrix_interpretable
**Saídas contratuais:** feature_diversity_redundancy_report
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S7_M03_INPUT_INVALID, P4_S7_M03_TEMPORAL_VIOLATION, P4_S7_M03_OUTPUT_INVALID, P4_S7_M03_FORBIDDEN_FIELD, P4_S7_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S7.M04 — `structural_feature_selector`

**Responsabilidade:** Selecionar features por cobertura, estabilidade, lineage, missingness, custo e redundância estrutural.

**Implementação técnica:** Selecionar somente por integridade/estabilidade/redundância/custo. Qualquer target-based importance é proibida e roteada à P5.

**Entradas contratuais:** underlying_feature_matrix_interpretable, feature_diversity_redundancy_report
**Saídas contratuais:** underlying_feature_matrix_selected, feature_selection_report
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S7_M04_INPUT_INVALID, P4_S7_M04_TEMPORAL_VIOLATION, P4_S7_M04_OUTPUT_INVALID, P4_S7_M04_FORBIDDEN_FIELD, P4_S7_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S8

Gerar representações cross-fitted, começando pelo baseline linear.

### P4.S8.M01 — `representation_fold_hyperparameter_controller`

**Responsabilidade:** Construir folds cronológicos cross-fitted, orçamento pequeno e pré-registrado de hiperparâmetros e plano de treinamento sem acesso a targets futuros.

**Implementação técnica:** Criar outer folds cronológicos e inner folds somente para duas configurações; persistir cutoffs e índices exatos.

**Entradas contratuais:** underlying_feature_matrix_selected, horizon_feature_set_manifest, feature_transform_state_manifest
**Saídas contratuais:** representation_fold_plan, encoder_hyperparameter_search_plan
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S8_M01_INPUT_INVALID, P4_S8_M01_TEMPORAL_VIOLATION, P4_S8_M01_OUTPUT_INVALID, P4_S8_M01_FORBIDDEN_FIELD, P4_S8_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S8.M02 — `family_pca_sparse_pca_builder`

**Responsabilidade:** Construir PCA e Sparse PCA por família e horizonte, com fit cross-fitted, loadings, explained variance, estabilidade e lineage.

**Implementação técnica:** PCA/Sparse PCA por família e horizonte, cross-fitted, com loadings, sign alignment, explained variance e estabilidade.

**Entradas contratuais:** underlying_feature_matrix_selected, feature_transform_state_manifest, representation_fold_plan
**Saídas contratuais:** underlying_feature_factors_pca, pca_fit_state_manifest
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S8_M02_INPUT_INVALID, P4_S8_M02_TEMPORAL_VIOLATION, P4_S8_M02_OUTPUT_INVALID, P4_S8_M02_FORBIDDEN_FIELD, P4_S8_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S8.M03 — `family_shared_private_denoising_encoder_builder`

**Responsabilidade:** Construir somente o challenger de encoder raso por família, denoising/masked e shared-private, preservando modalidades e sem objetivo preditivo.

**Implementação técnica:** Encoder raso shared-private com masking e modality dropout; sem target; duas configurações; output opcional.

**Entradas contratuais:** underlying_feature_matrix_selected, horizon_feature_set_manifest, feature_transform_state_manifest, representation_fold_plan, encoder_hyperparameter_search_plan
**Saídas contratuais:** underlying_feature_embeddings, encoder_fit_state_manifest
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S8_M03_INPUT_INVALID, P4_S8_M03_TEMPORAL_VIOLATION, P4_S8_M03_OUTPUT_INVALID, P4_S8_M03_FORBIDDEN_FIELD, P4_S8_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S8.M04 — `representation_quality_horizon_packager`

**Responsabilidade:** Avaliar estabilidade, reconstrução, degeneração, robustez, preservação de perspectivas e resultados da busca pequena; empacotar representações por horizonte.

**Implementação técnica:** Comparar representações por reconstrução, estabilidade, collapse, missing-view e preservação de perspectivas; não usar alpha.

**Entradas contratuais:** underlying_feature_factors_pca, underlying_feature_embeddings, pca_fit_state_manifest, encoder_fit_state_manifest, representation_fold_plan
**Saídas contratuais:** representation_quality_report, representation_horizon_bundle, encoder_hyperparameter_search_report
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S8_M04_INPUT_INVALID, P4_S8_M04_TEMPORAL_VIOLATION, P4_S8_M04_OUTPUT_INVALID, P4_S8_M04_FORBIDDEN_FIELD, P4_S8_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

## P4.S9

Auditar, versionar, empacotar e fechar a fronteira com P5/P0/P9.

### P4.S9.M01 — `feature_lineage_temporal_safety_auditor`

**Responsabilidade:** Reconstruir source→operator→fit→feature→representation e auditar segurança temporal ponta a ponta.

**Implementação técnica:** Auditar lineage source→operator→fit→feature→representation e reproduzir qualquer linha as-of.

**Entradas contratuais:** p4_output_candidate_bundle, all_fit_state_manifests
**Saídas contratuais:** feature_lineage_report, temporal_safety_report
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S9_M01_INPUT_INVALID, P4_S9_M01_TEMPORAL_VIOLATION, P4_S9_M01_OUTPUT_INVALID, P4_S9_M01_FORBIDDEN_FIELD, P4_S9_M01_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S9.M02 — `drift_coverage_quality_gate`

**Responsabilidade:** Medir drift de dados, cobertura, missingness, dependências e latents; não medir concept drift supervisionado.

**Implementação técnica:** Medir drift de valor, cobertura, missingness, dependência e latent; concept drift supervisionado pertence à P5/P9.

**Entradas contratuais:** p4_output_candidate_bundle, feature_lineage_report, representation_quality_report
**Saídas contratuais:** drift_safety_report, p4_quality_gate_decision
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S9_M02_INPUT_INVALID, P4_S9_M02_TEMPORAL_VIOLATION, P4_S9_M02_OUTPUT_INVALID, P4_S9_M02_FORBIDDEN_FIELD, P4_S9_M02_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S9.M03 — `model_consumer_view_packager`

**Responsabilidade:** Empacotar as mesmas informações em views tipadas para modelos tabulares, cross-sectionais, sequenciais, de grafo, cauda, regime, sparse e latentes sem escolher o modelo preditivo.

**Implementação técnica:** Gerar views tabular, ranked, sequence, graph, tail, regime, sparse e latent com contratos tipados.

**Entradas contratuais:** underlying_feature_matrix_raw, underlying_feature_matrix_selected, underlying_feature_factors_pca, underlying_feature_embeddings, horizon_feature_set_manifest, representation_quality_report, perspective_conflict_panel
**Saídas contratuais:** model_consumer_view_manifest, model_consumer_view_bundle
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S9_M03_INPUT_INVALID, P4_S9_M03_TEMPORAL_VIOLATION, P4_S9_M03_OUTPUT_INVALID, P4_S9_M03_FORBIDDEN_FIELD, P4_S9_M03_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S9.M04 — `phase5_feature_handoff_builder`

**Responsabilidade:** Construir manifesto P4→P5 com outputs legados, views por consumidor, hashes, schemas, qualidade, fit states e limitações.

**Implementação técnica:** Manifesto P4→P5 com hashes, schema, grain, intervalo, famílias, fit states, quality e limitações.

**Entradas contratuais:** p4_output_candidate_bundle, feature_lineage_report, drift_safety_report, p4_quality_gate_decision, model_consumer_view_manifest
**Saídas contratuais:** phase5_feature_handoff_manifest
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S9_M04_INPUT_INVALID, P4_S9_M04_TEMPORAL_VIOLATION, P4_S9_M04_OUTPUT_INVALID, P4_S9_M04_FORBIDDEN_FIELD, P4_S9_M04_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S9.M05 — `phase5_consumer_receipt_validator`

**Responsabilidade:** Validar o recibo da P5 e fechar a integração sem transformar consumo em qualificação econômica da P4.

**Implementação técnica:** Validar recibo real da P5 sem tratar consumo como prova de alpha.

**Entradas contratuais:** phase5_feature_handoff_manifest, phase5_consumption_receipt
**Saídas contratuais:** p4_to_p5_integration_receipt
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S9_M05_INPUT_INVALID, P4_S9_M05_TEMPORAL_VIOLATION, P4_S9_M05_OUTPUT_INVALID, P4_S9_M05_FORBIDDEN_FIELD, P4_S9_M05_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.

### P4.S9.M06 — `research_attempt_ledger_publisher`

**Responsabilidade:** Publicar ledger imutável de todas as tentativas, resultados negativos e rejeições, sem apagar graus de liberdade de pesquisa.

**Implementação técnica:** Publicar ledger append-only de toda tentativa, inclusive manual, falha, abandonada e reprovada; alimentar graveyard e P9.

**Entradas contratuais:** approved_hypothesis_passport_registry, hypothesis_budget_report, feature_selection_report, encoder_hyperparameter_search_report, representation_quality_report, drift_safety_report, phase5_feature_handoff_manifest
**Saídas contratuais:** p4_research_attempt_ledger, p4_rejected_feature_graveyard, p4_research_governance_report
**Invariantes:** point_in_time_integrity, lineage_traceability, single_responsibility, no_hidden_global_state, deterministic_replay_when_seeded
**Fail-fast:** P4_S9_M06_INPUT_INVALID, P4_S9_M06_TEMPORAL_VIOLATION, P4_S9_M06_OUTPUT_INVALID, P4_S9_M06_FORBIDDEN_FIELD, P4_S9_M06_UNDECLARED_DEPENDENCY

**Testes obrigatórios:**
- happy path com fixture mínima economicamente válida;
- schema e grain negativos;
- temporalidade/leakage adversarial;
- campos proibidos em níveis top-level e aninhados;
- lineage e replay determinístico;
- oracle numérico independente ou propriedade metamórfica;
- teste de limite, missingness e input parcialmente inválido;

**Definition of Done:** implementação, contrato, schema, documentação e testes alterados no mesmo commit; evidência de execução limpa; nenhuma promoção acima da maturidade comprovada.
