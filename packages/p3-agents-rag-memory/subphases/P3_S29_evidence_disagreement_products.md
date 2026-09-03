# P3.S29 — Evidence & Disagreement Products

## 1. Missão
Construir produtos legados de evidência e desacordo com semântica populacional.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S12.M01`, `P3.S13.M02`, `P3.S20.M05`, `P3.S22.M02`, `P3.S27.M01`, `P3.S28.M03`
- Downstream: `P3.S30.M01`, `P3.S30.M02`, `P3.S30.M03`, `P3.S30.M04`

## 4. Módulos
1. `P3.S29.M01` — `agent_disagreement_panel_builder`: Projetar desacordo populacional legado a partir das métricas canônicas.
2. `P3.S29.M02` — `evidence_claim_extractor`: Projetar cadeia crença→evidência→chunk/document/source.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `belief_distribution_panel`
- `validated_society_state_panel`
- `aggregation_semantics_config`
- `evidence_bound_belief_update_panel`
- `retrieval_evidence_map`
- `graph_evidence_map`
- `rag_index_artifact`

## 7. Outputs
- `agent_disagreement_panel`
- `evidence_tag_panel`

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
A especificação canônica está em `tests/specifications/subphases/P3_S29_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
