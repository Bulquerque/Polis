# P3.S33 Implementation Guide

## Componentes

A implementação está isolada em `extensions/research_tools` e preserva os registries legados de S1–S31 e o registry isolado de S32.

```text
contracts/boundary_artifacts.py
contracts/boundary_configs.py
services/input_contracts.py
services/views.py
services/custody.py
services/temporal_boundary.py
services/entity_resolution.py
services/boundary_bundle.py
s33.py
modules/P3_S33_M01...M05
```

## M01 — Phase 2 Research View Manifest

Converte 15 painéis públicos de P2 em referências pequenas. Cada view registra classe, artifact ID, hash, lineage, `available_at`, chaves de entidade, granularidade, operações autorizadas e readiness. Rows nunca são serializadas no manifesto.

## M02 — Phase 1 Raw Evidence Reference Index

Converte snapshots P1 em referências opacas. Caminhos são substituídos por `storage_ref_token`; o índice exige hash, snapshot, legibilidade e ligação com source IDs/lineage P2. Artifacts órfãos ficam `UNAUTHORIZED_ORPHAN`.

## M03 — Temporal Visibility and Vintage Firewall

Congela `decision_time`, timezone, política de missing time e vintages permitidos. A função pública `filter_visible_records` produz `PitQueryProof` com contagens de registros visíveis, futuros e sem timestamp.

## M04 — Temporal Entity and Instrument Resolver

Constrói índice determinístico a partir de configuração, underlyings, contratos de opções, documentos, eventos e ações corporativas. A resolução respeita `valid_from/valid_to` e retorna ambiguidade explicitamente.

## M05 — Boundary Bundle

Produz apenas referências, políticas e quatro ports esperados:

- `PitResearchQueryPort`
- `RawEvidenceResolverPort`
- `TemporalEntityResolverPort`
- `ProvenanceQueryPort`

Nenhum objeto de processo, segredo, path ou payload upstream entra no bundle.

## Determinismo

Todos os artifacts usam JSON canônico, SHA-256, ordenação estável, datetimes timezone-aware e IDs derivados do conteúdo. Wall clock não participa da semântica.
