# P3.S27 — Emergence Measurement

## 1. Missão
Calcular métricas canônicas com fórmulas, propositions e pesos congelados.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S7.M02`, `P3.S15.M02`, `P3.S18.M02`, `P3.S19.M01`, `P3.S21.M03`, `P3.S23.M01`, `P3.S23.M02`, `P3.S24.M02`, `P3.S24.M03`
- Downstream: `P3.S28.M02`, `P3.S29.M01`

## 4. Módulos
1. `P3.S27.M01` — `belief_distribution_aggregator`: Agregar crenças por underlying/proposition/horizon usando pesos de representação e fórmulas congeladas.
2. `P3.S27.M02` — `attention_information_asymmetry_metrics`: Calcular atenção e assimetria usando estado, acesso, execução real e pesos populacionais.
3. `P3.S27.M03` — `cascade_emergence_metrics`: Reconstruir cascatas com IDs causais de estímulo, mensagem e ativação.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `next_belief_state_panel`
- `validated_population_manifest`
- `stimulus_panel`
- `proposition_registry_config`
- `aggregation_semantics_config`
- `validated_next_person_state_panel`
- `tool_call_audit_panel`
- `person_tool_entitlement_panel`
- `activation_panel`
- `social_delivery_panel`
- `social_tool_audit_panel`

## 7. Outputs
- `belief_distribution_panel`
- `attention_information_metrics`
- `cascade_metrics_panel`

## 8. Limites de autoridade
- Sem targets futuros, scores, ranking, pesos ou sinais de trade.
- Sem estado global oculto ou reparo silencioso upstream.

## 9. Invariantes e configuração
PIT, lineage, produtor único, fail-closed, observabilidade e bindings em `config/CONFIG_BINDINGS.yaml`.

## 10. Falhas
Use os códigos tipados e a ordem de triagem definidos em cada YAML de módulo. Falha não pode produzir output parcial.

## 11. Observabilidade
Registrar run/cycle/module IDs, as_of_time, versões, hashes, duração, contagens, warnings e erros, com redaction.

## 12. Testes
A especificação canônica está em `tests/specifications/subphases/P3_S27_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
