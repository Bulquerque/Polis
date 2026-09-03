# P3.S5 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S5.

## 3. Dependências
P3.S4.M01, P3.S4.M02, P3.S5.M01

## 4. Módulos
- `P3.S5.M01` — personality_candidate_generator: Gerar candidatos via LLM com seed, prompt version, provenance, retry limitado e modo coverage/density.
- `P3.S5.M02` — personality_candidate_consistency_checker: Validar coerência semântica e estrutural dos candidatos por regras canônicas.

## 6. Inputs
- `person_schema_policy`
- `personality_candidate_pool`
- `personality_consistency_rules_config`
- `personality_creator_retry_policy_config`
- `personality_tag_registry`
- `population_generation_config`
- `prior_population_generation_state`
- `provider_adapter_registry_config`

## 7. Outputs
- `personality_candidate_pool`
- `personality_creator_generation_audit`
- `validated_personality_candidate_pool`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
