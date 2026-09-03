# P3.S35 módulo por módulo

## P3.S35.M01 — corpus_snapshot_index_loader

Carrega `retrieval_index_manifest`, verifica snapshot, as-of, hashes, contagem de chunks, IDs e referências do índice. Produz um repository imutável para runtime.

Falha em:

- snapshot ou as-of incompatível;
- hash adulterado;
- chunk futuro dentro do snapshot;
- chunk ID duplicado;
- posting para chunk inexistente.

## P3.S35.M02 — hybrid_retrieval_policy_builder

Constrói políticas por modo:

| Modo | Resultados | Subconsultas | Trabalho | Semântico |
|---|---:|---:|---:|---|
| LOOKUP | 5 | 1 | 3 | não necessário |
| STANDARD | 15 | 2 | 8 | opcional |
| TRIANGULATED | 30 | 4 | 20 | opcional |
| FORENSIC | 50 | 5 | 35 | opcional; versões obrigatórias na qualificação |

Os valores podem ser reduzidos por configuração, mas continuam sujeitos aos limites duros dos modelos.

## P3.S35.M03 — document_version_provenance_handler_bundle_builder

Registra e qualifica:

- `search`;
- `get_document`;
- `compare_versions`;
- `inspect_provenance`.

`FORENSIC` fica bloqueado sem grafo de versões. Proveniência sem referência completa à P1 é degradada, não inventada.

## P3.S35.M04 — counterevidence_timeline_handler_bundle_builder

Registra e qualifica:

- `find_counterevidence`;
- `build_timeline`.

Contraprovas exigem consultas fornecidas explicitamente pelo planner e retornam somente evidências recuperadas. Timeline ordena documentos por tempo observável e não afirma causalidade automaticamente.

## P3.S35.M05 — corpus_tool_bundle_qualification_builder

Consolida os seis handlers, verifica unicidade e produz:

- manifest de handlers;
- matriz operação × modo;
- prontidão da família.

Uma operação bloqueada em um modo avançado não impede o uso de seus modos rasos qualificados.
