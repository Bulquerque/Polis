# P3.S13 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S13.

## 3. Dependências
P3.S12.M01, P3.S13.M01, P3.S2.M01

## 4. Módulos
- `P3.S13.M01` — temporal_graph_builder: Construir grafo temporal de entidades, eventos e relações com evidence refs.
- `P3.S13.M02` — graph_evidence_linker: Mapear cada node/edge/claim a chunks, documentos, fontes e disponibilidade.

## 6. Inputs
- `graph_config`
- `graph_rag_artifact`
- `pit_validated_context`
- `provider_adapter_registry_config`
- `rag_index_artifact`

## 7. Outputs
- `graph_evidence_map`
- `graph_rag_artifact`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
