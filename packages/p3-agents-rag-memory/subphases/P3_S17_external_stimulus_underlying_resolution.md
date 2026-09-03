# P3.S17 — External Stimulus & Underlying Resolution

## 1. Missão
Materializar estímulos externos e resolver entidades para underlyings canônicos.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S2.M01`, `P3.S2.M02`, `P3.S13.M01`
- Downstream: `P3.S18.M02`

## 4. Módulos
1. `P3.S17.M01` — `external_stimulus_builder`: Transformar contexto PIT em estímulos externos com evidence refs e salience.
2. `P3.S17.M02` — `canonical_underlying_resolver`: Resolver subject/entity para underlying canônico com estado unresolved explícito.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `pit_validated_context`
- `graph_rag_artifact`
- `phase3_run_snapshot`
- `stimulus_bus_config`
- `external_stimulus_stream`
- `entity_underlying_map_config`
- `proposition_registry_config`

## 7. Outputs
- `external_stimulus_stream`
- `resolved_external_stimulus_stream`

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
A especificação canônica está em `tests/specifications/subphases/P3_S17_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
