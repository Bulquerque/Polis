# P3.S6 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S6.

## 3. Dependências
P3.S4.M01, P3.S5.M02, P3.S6.M01

## 4. Módulos
- `P3.S6.M01` — personality_coverage_metric_calculator: Calcular coverage por células de tags/papéis, novelty marginal, densidade kNN e covariância ponderada.
- `P3.S6.M02` — coverage_density_controller: Aplicar a máquina de estados NOVELTY→DENSITY→FINALIZED com saídas mutuamente exclusivas.

## 6. Inputs
- `coverage_density_config`
- `personality_coverage_report`
- `personality_tag_registry`
- `population_candidate_accumulator`
- `prior_population_generation_state`
- `validated_personality_candidate_pool`

## 7. Outputs
- `finalized_personality_candidate_pool`
- `next_population_generation_state`
- `personality_coverage_report`
- `population_candidate_accumulator`
- `population_generation_control`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
