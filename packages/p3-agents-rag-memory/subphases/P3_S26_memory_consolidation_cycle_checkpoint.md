# P3.S26 — Memory Consolidation & Cycle Checkpoint

## 1. Missão
Consolidar experiências, feedback maturado e produzir estado/fila para N+1.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S2.M02`, `P3.S3.M01`, `P3.S3.M02`, `P3.S11.M03`, `P3.S20.M04`, `P3.S21.M03`, `P3.S21.M05`, `P3.S22.M03`, `P3.S23.M01`, `P3.S23.M02`, `P3.S24.M02`, `P3.S25.M03`
- Downstream: `P3.S30.M02`

## 4. Módulos
1. `P3.S26.M01` — `memory_consolidation_manager`: Consolidar episódios, feedback maturado, ferramentas, interações e lições em memória individual.
2. `P3.S26.M02` — `endogenous_stimulus_queue_checkpoint_writer`: Criar fila N+1 a partir de descobertas, mensagens, memória e atenção.
3. `P3.S26.M03` — `cycle_state_checkpoint_writer`: Congelar estado completo N para consumo exclusivo em N+1.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `current_memory_state`
- `person_learning_trajectory_bundle`
- `next_belief_state_panel`
- `validated_next_person_state_panel`
- `social_delivery_panel`
- `active_belief_feedback_bundle`
- `active_retro_policy_patch`
- `memory_consolidation_config`
- `tool_discovery_event_panel`
- `social_delivery_event_panel`
- `memory_trigger_event_panel`
- `finalized_attention_followup_intent_panel`
- `phase3_run_snapshot`
- `stimulus_bus_config`
- `next_memory_state`
- `next_social_graph`
- `next_cycle_endogenous_stimulus_queue`
- `belief_outcome_commitment_log`

## 7. Outputs
- `next_memory_state`
- `memory_trigger_event_panel`
- `next_cycle_endogenous_stimulus_queue`
- `cycle_state_snapshot_out`

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
A especificação canônica está em `tests/specifications/subphases/P3_S26_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
