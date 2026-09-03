# P3.S20 — Activated-Person Retrieval & Context Assembly

## 1. Missão
Consultar memória/RAG/GraphRAG após a ativação e montar o contexto final da pessoa.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S2.M02`, `P3.S2.M03`, `P3.S3.M01`, `P3.S11.M03`, `P3.S12.M02`, `P3.S13.M01`, `P3.S13.M02`, `P3.S14.M01`, `P3.S14.M02`, `P3.S15.M02`, `P3.S18.M02`, `P3.S19.M01`, `P3.S19.M02`
- Downstream: `P3.S21.M01`, `P3.S21.M04`, `P3.S21.M05`, `P3.S22.M02`, `P3.S26.M01`, `P3.S29.M02`

## 4. Módulos
1. `P3.S20.M01` — `activated_person_query_builder`: Construir query por pessoa ativada usando estímulo, crenças, atenção e objetivo atual.
2. `P3.S20.M02` — `hybrid_memory_rag_retriever`: Consultar memória individual e índice documental com filtros PIT e budgets.
3. `P3.S20.M03` — `graph_rag_query_executor`: Executar traversal GraphRAG limitado e evidenciado por pessoa ativada.
4. `P3.S20.M04` — `person_experience_retriever`: Recuperar somente trajetórias vividas pela própria pessoa, incluindo feedback maturado já consolidado.
5. `P3.S20.M05` — `retrieval_reranker_evidence_bundle_builder`: Reranquear memória/RAG/GraphRAG e construir bundle final com mapa de evidências.
6. `P3.S20.M06` — `person_context_assembler`: Montar contexto da pessoa com estímulo, ativação, estado, crenças, retrieval, relações, ferramentas e patch permitido.
7. `P3.S20.M07` — `context_budget_validator`: Validar orçamento, cutoff risk, schema e prioridade do contexto final.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `cognitive_cycle_schedule`
- `stimulus_panel`
- `activation_panel`
- `current_person_state_panel`
- `current_belief_state_panel`
- `phase3_run_snapshot`
- `person_retrieval_query_panel`
- `memory_index_manifest`
- `retrieval_index_manifest`
- `memory_access_policy`
- `retrieval_config`
- `provider_adapter_registry_config`
- `graph_rag_artifact`
- `graph_evidence_map`
- `graph_config`
- `current_memory_state`
- `context_learning_config`
- `raw_retrieved_knowledge_bundle`
- `graph_retrieval_bundle`
- `person_learning_trajectory_bundle`
- `retrieved_knowledge_bundle`
- `current_social_graph`
- `person_tool_entitlement_panel`
- `active_retro_policy_patch`
- `person_context_bundle`
- `context_budget_config`
- `model_knowledge_cutoff_report`

## 7. Outputs
- `person_retrieval_query_panel`
- `raw_retrieved_knowledge_bundle`
- `graph_retrieval_bundle`
- `person_learning_trajectory_bundle`
- `retrieved_knowledge_bundle`
- `retrieval_evidence_map`
- `person_context_bundle`
- `validated_person_context_bundle`

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
A especificação canônica está em `tests/specifications/subphases/P3_S20_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
