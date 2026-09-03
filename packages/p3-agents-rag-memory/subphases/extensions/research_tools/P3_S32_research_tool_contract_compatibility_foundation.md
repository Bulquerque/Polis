# P3.S32 — Research Tool Contract & Compatibility Foundation

## Missão

Criar a única autoridade contratual da extensão de ferramentas de pesquisa da P3 sem modificar os módulos canônicos P3.S1–P3.S31. A subfase define seis famílias, 34 operações, seus schemas, modos, aliases, providers e snapshot de replay.

## Ordem

```text
M01 catálogo e operações
  ├─ M02 modos
  └─ M03 compatibilidade S15/S16
M01 + M02 + M03 → M04 snapshot
```

## Autoridade

- Pydantic é a fonte de verdade dos contratos serializados.
- JSON Schema Draft 2020-12 é gerado dos modelos.
- YAML contém políticas e enablement, não contratos duplicados.
- MCP é transporte opcional; a identidade funcional é `tool_id + operation_id`.
- Providers externos não comprovados permanecem `OPTIONAL_NOT_CONFIGURED`.

## Famílias

`research.corpus.v1`, `market.observation.v1`, `options.observation.v1`, `macro.observation.v1`, `company.fundamentals.v1`, `quant.diagnostics.v1`.

## Compatibilidade

- `research.search_filings.v1` é alias de `research.corpus.v1/search`.
- `quant.realized_volatility.v1` é alias de `quant.diagnostics.v1/realized_volatility`.
- O limite legado de chamadas visíveis é preservado e limitado a cinco.
- `DISCOVER/REQUEST/EXECUTE` são ações administrativas e não operações funcionais.

## Limites

S32 não executa ferramentas, não acessa P1/P2, não concede entitlement, não usa rede e não promove produção.

## Referências técnicas

- JSON Schema Draft 2020-12: https://json-schema.org/draft/2020-12
- Pydantic JSON Schema: https://docs.pydantic.dev/latest/concepts/json_schema/
- Pydantic strict mode: https://docs.pydantic.dev/latest/concepts/strict_mode/
- MCP specification: https://modelcontextprotocol.io/specification/
- Semantic Versioning 2.0.0: https://semver.org/spec/v2.0.0.html
