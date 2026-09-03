# P3.S30 — Feature Projection & P4 Handoff

## 1. Missão
Projetar outputs oficiais e congelar o handoff P3→P4.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S2.M02`, `P3.S22.M03`, `P3.S26.M01`, `P3.S28.M03`, `P3.S29.M01`, `P3.S29.M02`
- Downstream: `P3.S31.M01`, `P3.S31.M02`

## 4. Módulos
1. `P3.S30.M01` — `social_feature_builder`: Projetar estado social validado no schema oficial sem target futuro.
2. `P3.S30.M02` — `context_memory_feature_builder`: Projetar somente atributos canônicos de memória/contexto para P4.
3. `P3.S30.M03` — `hypothesis_registry_builder`: Construir hipóteses falsificáveis com horizon, evidência, oposição e critérios de maturação.
4. `P3.S30.M04` — `phase4_social_handoff_builder`: Congelar os seis outputs oficiais e manifest P3→P4.
5. `P3.S30.M05` — `variable_evolution_handoff_builder`: Entregar estados canônicos e commitments à futura camada P4 Variable Evolution Lab.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `validated_society_state_panel`
- `evidence_tag_panel`
- `agent_disagreement_panel`
- `next_memory_state`
- `social_feature_panel`
- `context_memory_feature_panel`
- `proposition_registry_config`
- `hypothesis_registry`
- `phase3_run_snapshot`
- `belief_outcome_commitment_log`

## 7. Outputs
- `social_feature_panel`
- `context_memory_feature_panel`
- `hypothesis_registry`
- `phase4_social_handoff_manifest`
- `variable_evolution_input_manifest`

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
A especificação canônica está em `tests/specifications/subphases/P3_S30_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
