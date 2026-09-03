# P3.S19 — Deterministic Activation & Heartbeat

## 1. Missão
Decidir deterministicamente quem é ativado e garantir heartbeat mensal.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S7.M01`, `P3.S7.M02`, `P3.S11.M03`, `P3.S18.M02`
- Downstream: `P3.S20.M01`, `P3.S20.M06`, `P3.S27.M03`

## 4. Módulos
1. `P3.S19.M01` — `deterministic_activation_gate`: Calcular activation_score configurado por estímulo e pessoa antes de qualquer LLM.
2. `P3.S19.M02` — `monthly_heartbeat_scheduler`: Combinar ativações extraordinárias com pelo menos um ciclo mensal por pessoa.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `stimulus_panel`
- `current_person_state_panel`
- `person_seed_panel`
- `activation_config`
- `activation_panel`
- `validated_population_manifest`
- `heartbeat_config`

## 7. Outputs
- `activation_panel`
- `cognitive_cycle_schedule`

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
A especificação canônica está em `tests/specifications/subphases/P3_S19_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
