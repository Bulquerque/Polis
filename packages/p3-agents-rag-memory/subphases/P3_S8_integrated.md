# P3.S8 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S8.

## 3. Dependências
P3.S4.M01, P3.S7.M01, P3.S7.M02, P3.S8.M01

## 4. Módulos
- `P3.S8.M01` — initial_social_graph_builder: Construir grafo seeded por homofilia, instituição, papel, geografia e bridges configurados.
- `P3.S8.M02` — relationship_prior_validator: Validar topologia, tipos de relação e confiança específica por domínio.

## 6. Inputs
- `initial_social_graph`
- `person_seed_panel`
- `personality_tag_registry`
- `social_graph_config`
- `validated_population_manifest`

## 7. Outputs
- `initial_social_graph`
- `validated_initial_social_graph`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
