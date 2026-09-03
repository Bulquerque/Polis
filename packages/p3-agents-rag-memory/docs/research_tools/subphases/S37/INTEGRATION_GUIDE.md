# Guia de integração

## Pré-requisitos

A integração precisa receber do Agente 1:

- `research_data_boundary_bundle.v1`
- `tool_operation_registry.v1`
- `research_mode_registry.v1`
- `research_tool_extension_snapshot.v1`

E do Agente 3:

- contrato definitivo de `HandlerBundleManifest`
- registry por `(tool_id, operation_id)`
- ponte S21/S40

## Outputs

### M01

- `macro_series_release_catalog`
- `macro_view_readiness_report`
- `macro_asset_context_config_snapshot`

### M02

- `macro_observation_handler_bundle`
- `macro_observation_operation_mode_qualification`

### M03

- `macro_context_handler_bundle`
- `macro_context_operation_mode_qualification`

### M04

- `macro_tool_handler_bundle`
- `macro_operation_mode_qualification`
- `macro_tool_readiness_report`

## Ponte S21

O S40 deverá converter o `MacroToolResultEnvelope` para `ToolExecutionResponse`:

- `status=SUCCEEDED` quando a chamada foi processada;
- `provider_id=internal_research`;
- envelope completo em `canonical_payload`;
- `evidence_refs=()` na ponte inicial, preservando evidências detalhadas no payload.

A semântica de negócio permanece em `outcome_status`: `PASS`, `EMPTY_VALID`, `DEGRADED` ou `BLOCKED_UPSTREAM`.

## Merge

O overlay é `ADDITIVE_ONLY`. Os quatro wrappers possuem IDs inéditos e não podem substituir módulos anteriores.

## Registry de schemas

Os schemas desta subfase ficam em `extension_schemas/` para não alterar o registry canônico de P3.S1–S31 antes de S40/P0. A promoção global deve mesclar esse registry, recalcular `schema_count` e regenerar o release hash.
