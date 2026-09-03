# P3.S28 — Tag Projection & Underlying Society Vector

## 1. Missão
Cruzar crenças individuais com tags e formar vetor compacto por underlying.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S2.M02`, `P3.S4.M01`, `P3.S7.M01`, `P3.S7.M02`, `P3.S23.M01`, `P3.S23.M02`, `P3.S27.M01`, `P3.S27.M02`, `P3.S27.M03`
- Downstream: `P3.S29.M01`, `P3.S30.M01`, `P3.S30.M02`, `P3.S30.M05`, `P3.S31.M01`

## 4. Módulos
1. `P3.S28.M01` — `tag_conditioned_projection_engine`: Cruzar crenças individuais, tags e pesos para projeções condicionadas com tamanho mínimo.
2. `P3.S28.M02` — `underlying_society_state_vector_builder`: Construir vetor compacto canônico por underlying/as_of/proposition horizon.
3. `P3.S28.M03` — `society_vector_quality_guard`: Validar cobertura, qualidade de fonte, incerteza e materialidade do vetor.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `next_belief_state_panel`
- `person_seed_panel`
- `validated_population_manifest`
- `validated_next_person_state_panel`
- `personality_tag_registry`
- `proposition_registry_config`
- `aggregation_semantics_config`
- `belief_distribution_panel`
- `attention_information_metrics`
- `cascade_metrics_panel`
- `tag_projection_panel`
- `emergence_vector_config`
- `synthetic_society_state_panel`
- `source_quality_panel`
- `phase3_run_snapshot`

## 7. Outputs
- `tag_projection_panel`
- `synthetic_society_state_panel`
- `validated_society_state_panel`

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
A especificação canônica está em `tests/specifications/subphases/P3_S28_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
