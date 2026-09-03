# P3.S18 — Endogenous Stimulus Event Bus

## 1. Missão
Mesclar a fila endógena N−1 com estímulos externos sem feedback same-cycle.

## 2. Escopo
Uma responsabilidade fechada, com handoff explícito e sem absorver funções de outras subfases.

## 3. Dependências
- Upstream: `P3.S17.M02`
- Downstream: `P3.S19.M01`, `P3.S20.M01`, `P3.S20.M06`, `P3.S27.M01`, `P3.S27.M03`

## 4. Módulos
1. `P3.S18.M01` — `endogenous_stimulus_queue_loader`: Carregar somente fila endógena produzida no ciclo anterior.
2. `P3.S18.M02` — `stimulus_event_bus_merger`: Mesclar estímulos externos/endógenos, deduplicar e priorizar deterministicamente.

## 5. Ordem de execução
A ordem acima é canônica e deve respeitar todas as dependências locais do DAG.

## 6. Inputs
- `prior_cycle_endogenous_stimulus_queue`
- `stimulus_bus_config`
- `resolved_external_stimulus_stream`
- `endogenous_stimulus_stream`

## 7. Outputs
- `endogenous_stimulus_stream`
- `stimulus_panel`

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
A especificação canônica está em `tests/specifications/subphases/P3_S18_TEST_SPEC.yaml` e cobre happy path, negativos, boundaries, PIT, lineage, autoridade e observabilidade.

## 13. Definition of Done
- Código, contratos, schemas, configs, testes e documentação atualizados juntos.
- Handoff reproduzível e sem dependência implícita.
- Evidência de fail-fast e nenhuma alegação de produção antes dos gates P0.
