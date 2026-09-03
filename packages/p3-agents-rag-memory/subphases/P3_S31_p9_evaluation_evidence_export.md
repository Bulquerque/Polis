# P3.S31 — P9 Evaluation Evidence Export

## 1. Missão
Exportar evidências reproduzíveis para a P9 sem avaliar, promover ou alterar o ciclo atual.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S2.M02`, `P3.S2.M03`, `P3.S22.M03`, `P3.S28.M03`, `P3.S30.M04`, `P3.S30.M05`
- Downstream: handoffs externos

## 4. Módulos
1. `P3.S31.M01` — `p9_evaluation_evidence_bundle_builder`: Empacotar evidências, commitments, seeds, cutoff risk e outputs para avaliação externa da P9.
2. `P3.S31.M02` — `p9_context_learning_handoff_builder`: Congelar o handoff P3→P9 para avaliação e aprendizado cross-phase.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `phase4_social_handoff_manifest`
- `variable_evolution_input_manifest`
- `belief_outcome_commitment_log`
- `model_knowledge_cutoff_report`
- `phase3_run_snapshot`
- `validated_society_state_panel`
- `p9_evaluation_evidence_bundle`

## 7. Outputs
- `p9_evaluation_evidence_bundle`
- `p9_context_learning_handoff_manifest`

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
A especificação canônica está em `tests/specifications/subphases/P3_S31_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
