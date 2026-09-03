# P3.S37 — Macro Observation Tool Suite

## Objetivo

Disponibilizar aos agentes observações macroeconômicas point-in-time sem duplicar ingestão, limpeza, previsão ou motores downstream.

## Escopo

A subfase constrói catálogo, handlers e qualificação para:

- descoberta de séries;
- observações históricas conhecidas no instante;
- snapshots de release e vintages;
- comparação descritiva entre séries;
- contexto macro estrutural de ativos.

## Fora de escopo

- previsão macro;
- nowcasting;
- HMM ou classificação de regime;
- causalidade automática;
- geração de sinal;
- feature engine oficial;
- seleção de modelo;
- backtest;
- otimização de portfólio.

## Módulos

1. `P3.S37.M01 macro_series_release_catalog_builder`
2. `P3.S37.M02 macro_observation_vintage_handler_bundle_builder`
3. `P3.S37.M03 macro_comparison_asset_context_handler_bundle_builder`
4. `P3.S37.M04 macro_tool_bundle_vintage_qualification_builder`

## Gate

Toda combinação `operação × modo` possui status independente. Um arquivo existente não é prova de que vintages, unidades ou releases estejam completos.
