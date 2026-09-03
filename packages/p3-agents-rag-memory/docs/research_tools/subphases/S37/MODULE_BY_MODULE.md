# Plano módulo por módulo

## P3.S37.M01

Constrói o catálogo de séries e releases a partir das views macro P2. Valida identificador, data, valor e disponibilidade. Registros inválidos não qualificam uma série. Produz readiness por operação e snapshot do mapa macro de ativos.

## P3.S37.M02

Publica os handlers de `search_series`, `get_observations` e `get_release_snapshot`. Define modos permitidos e bloqueia análise de vintage quando revisões reais não existem.

## P3.S37.M03

Publica `compare_series` e `get_asset_context`. Comparações são alinhadas por datas e transformações autorizadas. O contexto de ativos vem de um registro ex ante, versionado e filtrado temporalmente.

## P3.S37.M04

Consolida manifests, deduplica handlers e produz a matriz final de qualificação. Operações bloqueadas não devem aparecer no entitlement efetivo montado por S34/S40.
