# Operações

## search_series

Descobre séries visíveis no `decision_time`, filtrando região, país, família, frequência e fonte.

## get_observations

Retorna observações segundo `KNOWN_AT_DECISION_TIME`, `ORIGINAL_RELEASE` ou `LATEST_KNOWN_AT_DECISION_TIME`. Transformações só são executadas quando autorizadas no catálogo.

## get_release_snapshot

Recupera um snapshot histórico de release/vintage. É bloqueado sem suporte real a vintages.

## compare_series

Alinha de duas a dez séries e oferece comparações descritivas: valores brutos, diferença, spread, razão e base 100. Não estima causalidade ou previsão.

## get_asset_context

Recupera fatores macro previamente governados para um ativo. O mapa possui `available_at` e intervalo de vigência; não é inferido retrospectivamente a partir do retorno observado.
