# Qualificação local final

## Estado

```text
IMPLEMENTED_QUALIFIED_LOCAL
production_promotion_allowed = false
production_authority = P0_ONLY
requires_s40_composition = true
```

## Escopo qualificado

- `P3.S37.M01–M04`;
- `macro.observation.v1`;
- cinco operações públicas;
- 24 schemas gerados;
- quatro fixtures douradas.

## Resultados

- 23/23 testes próprios;
- 4/4 testes selecionados de compatibilidade P1;
- 3/3 testes selecionados de compatibilidade P2;
- 7/7 testes selecionados S21/registry;
- merge simulado: 81/81 módulos originais byte a byte idênticos;
- quatro módulos S37 adicionados;
- 23/23 testes S37 e 7/7 S21/registry no namespace mesclado;
- cobertura branch-aware: 83%;
- wheel construído, instalado e importado em diretório isolado.

## Qualificação por modo

`LOOKUP` e `CONTEXT` podem ser qualificados localmente quando os campos mínimos existem e a prova PIT passa.

`VINTAGE_ANALYSIS` exige histórico real de revisões. Cobertura parcial gera `DEGRADED`; ausência total gera `BLOCKED_UPSTREAM`.

`get_asset_context` exige um registro governado, versionado e conhecido no `decision_time`. O handler não estima relações ex post.

## Gates globais deliberadamente não ocultados

A P3 antiga continua declarando 81 módulos e possui um hash de release calculado antes do overlay. A integração final precisa:

1. registrar os quatro módulos S37 no catálogo global da extensão;
2. atualizar a expectativa estrutural por meio de S40/P0;
3. integrar o registry isolado de schemas;
4. regenerar o release hash global.

Esses itens não são corrigidos dentro da S37 porque a subfase não possui autoridade para alterar `P3.S1–P3.S31` nem promover a release global.

## Ferramentas de qualidade indisponíveis no ambiente

`ruff` e `mypy` não estavam instalados. A entrega não afirma que esses comandos foram executados. Foram usados os gates disponíveis: AST, compilação, testes contratuais, análise de complexidade, cobertura, build e import isolado.
