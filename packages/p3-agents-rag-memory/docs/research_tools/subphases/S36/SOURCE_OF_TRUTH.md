# Source of Truth

## Autoridade

1. Modelos Pydantic em `families/market/` são a autoridade de contratos serializados.
2. Configurações YAML são a autoridade de políticas e enablement.
3. JSON Schemas são gerados dos modelos; não são mantidos manualmente.
4. `contracts/MODULE_REGISTRY_OVERLAY.yaml` é o overlay aditivo de módulos.
5. `config/CANONICAL_DAG_OVERLAY.yaml` define a composição sem alterar módulos antigos.

## IDs canônicos

```text
P3.S36.M01 market_view_binding_builder
P3.S36.M02 market_snapshot_history_liquidity_handler_bundle_builder
P3.S36.M03 corporate_action_cross_asset_handler_bundle_builder
P3.S36.M04 option_contract_chain_handler_bundle_builder
P3.S36.M05 option_surface_diagnostic_handler_bundle_builder
P3.S36.M06 market_derivatives_tool_bundle_qualification_builder
```

## Autoridades de fase

- P1: custódia, bytes, snapshots e hashes;
- P2: limpeza, identidade, qualidade e `available_at`;
- P3.S36: observação e diagnóstico descritivo;
- P5: previsão e regime, não consultada por S36;
- P6: candidatos de opções, não produzidos por S36;
- P8/P9: backtest, risco e robustez, não executados por S36.

## Estado de promoção

```text
implementation_status = IMPLEMENTED_QUALIFIED_LOCAL
production_promotion_allowed = false
production_authority = P0_ONLY
```
