# P3.S12 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S12.

## 3. Dependências
P3.S12.M01, P3.S2.M01, P3.S2.M02

## 4. Módulos
- `P3.S12.M01` — document_chunker_and_indexer: Chunkar e indexar documentos preservando source, entity, available_at e lineage.
- `P3.S12.M02` — retrieval_index_manifest_builder: Congelar índices, embedding/reranker versions e capabilities disponíveis.

## 6. Inputs
- `phase3_run_snapshot`
- `pit_validated_context`
- `provider_adapter_registry_config`
- `rag_index_artifact`
- `retrieval_config`

## 7. Outputs
- `rag_index_artifact`
- `retrieval_index_manifest`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
