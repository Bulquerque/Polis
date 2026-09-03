# P3.S25 — Trust & Relationship Evolution

## 1. Missão
Atualizar confiança e permitir novos vínculos somente por mecanismos plausíveis.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S3.M01`, `P3.S3.M02`, `P3.S11.M03`, `P3.S23.M02`, `P3.S24.M02`, `P3.S24.M03`
- Downstream: `P3.S26.M03`

## 4. Módulos
1. `P3.S25.M01` — `trust_relationship_updater`: Atualizar trust/domain trust gradualmente usando interações e feedback maturado de precisão.
2. `P3.S25.M02` — `social_relationship_tool_executor`: Avaliar candidate edges via capacidade social promovida e critérios plausíveis.
3. `P3.S25.M03` — `relationship_change_validator`: Validar mudanças e materializar o grafo seguinte.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `current_social_graph`
- `social_delivery_panel`
- `validated_next_person_state_panel`
- `active_belief_feedback_bundle`
- `relationship_update_config`
- `updated_social_graph`
- `social_tool_audit_panel`
- `active_retro_policy_patch`
- `relationship_formation_config`
- `relationship_candidate_panel`
- `social_graph_config`

## 7. Outputs
- `updated_social_graph`
- `relationship_candidate_panel`
- `next_social_graph`

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
A especificação canônica está em `tests/specifications/subphases/P3_S25_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
