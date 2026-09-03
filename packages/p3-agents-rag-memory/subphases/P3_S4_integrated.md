# P3.S4 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S4.

## 3. Dependências
P3.S4.M01

## 4. Módulos
- `P3.S4.M01` — personality_tag_registry_loader: Carregar o vocabulário fixo e versionado de tags.
- `P3.S4.M02` — person_schema_policy_loader: Carregar schema, objetivos por papel, pesos de representação e coerência da pessoa.

## 6. Inputs
- `economic_role_taxonomy_config`
- `person_schema_policy_config`
- `personality_tag_registry`
- `personality_tag_registry_config`
- `population_representation_config`
- `role_objective_registry_config`

## 7. Outputs
- `person_schema_policy`
- `personality_tag_registry`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
