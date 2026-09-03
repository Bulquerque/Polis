# Fonte de verdade

## Autoridade

1. Modelos Pydantic em `extensions/research_tools/families/macro/`.
2. Contratos de módulo em `contracts/modules/`.
3. Políticas YAML em `config/research_tools/macro/`.
4. JSON Schemas gerados em `extension_schemas/research_tools/macro/` (incluindo `SCHEMA_BINDINGS.yaml`).
5. Fixtures douradas em `fixtures/golden/`.

## Identidade congelada

- subfase: `P3.S37`
- módulos: `P3.S37.M01–M04`
- família: `macro.observation.v1`
- versão: `1.0.0`
- transporte esperado: `ARTIFACT_QUERY` ou `COMPOSITE_INTERNAL`
- execução de rede em backtest: proibida

## Autoridades cross-phase

- P1: custódia, captura, bytes, snapshots e hashes.
- P2: normalização, qualidade, semântica e `available_at`.
- P3.S37: consulta, vintages, transformações autorizadas e comparação descritiva.
- P3.S40: registro, gateway, evidência final e handoffs.

## Regra temporal

`available_at <= decision_time`

`event_time`, `reference_date`, `published_at`, `available_at`, `ingested_at` e `decision_time` não são intercambiáveis.
