# P3.S14 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S14.

## 3. Dependências
P3.S11.M03, P3.S14.M01, P3.S2.M02, P3.S4.M02

## 4. Módulos
- `P3.S14.M01` — memory_access_policy_builder: Construir política versionada de retrievability, budgets e separação audit/access.
- `P3.S14.M02` — memory_index_manifest_builder: Indexar o estado de memória para consultas posteriores sem selecionar conteúdo.

## 6. Inputs
- `current_memory_state`
- `memory_access_config`
- `memory_access_policy`
- `person_schema_policy`
- `phase3_run_snapshot`
- `retrieval_config`

## 7. Outputs
- `memory_access_policy`
- `memory_index_manifest`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
