# Compatibilidade de APIs e fontes upstream

A S37 não chama APIs durante backtest. As APIs oficiais orientam os contratos de P1/P2 e a semântica preservada nos snapshots.

## FRED/ALFRED

A API oficial expõe `realtime_start`, `realtime_end` e `vintage_dates`, confirmando que observação histórica e informação conhecida em uma data são consultas distintas.

- https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html

## BLS

A API possui versões e limites próprios de séries/anos. Batching e credenciais pertencem à P1, não à S37.

- https://www.bls.gov/developers/api_signature_v2.htm
- https://www.bls.gov/developers/api_faqs.htm

## BEA

A API oficial é orientada a datasets, parâmetros e resultados JSON/XML. O adapter P1 materializa snapshots antes de a P3 operar.

- https://apps.bea.gov/api/
- https://github.com/us-bea/beaapi

## EIA

A API v2 possui rotas, facets, frequência, paginação e contratos próprios. A P3 consome somente os artefatos congelados.

- https://www.eia.gov/opendata/documentation.php

## Política

Mudanças futuras nas APIs exigem adaptação em P1/P2 e nova qualificação upstream. Elas não devem alterar silenciosamente os handlers S37.
