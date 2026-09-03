# P3.S7 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S7.

## 3. Dependências
P3.S4.M02, P3.S5.M01, P3.S6.M01, P3.S6.M02, P3.S7.M01

## 4. Módulos
- `P3.S7.M01` — fixed_population_builder: Congelar pessoas, IDs e pesos de representação que somam 1.
- `P3.S7.M02` — population_consistency_validator: Validar cobertura, clones, concentração e representatividade da população congelada.

## 6. Inputs
- `finalized_personality_candidate_pool`
- `person_schema_policy`
- `person_seed_panel`
- `personality_coverage_report`
- `personality_creator_generation_audit`
- `population_generation_control`
- `population_manifest`
- `population_representation_config`

## 7. Outputs
- `person_seed_panel`
- `population_manifest`
- `validated_population_manifest`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
