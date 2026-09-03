# Changelog

## 1.0.0 — 2026-08-04

- Implementados os quatro módulos de `P3.S37`.
- Criada a família `macro.observation.v1` com cinco operações.
- Implementado firewall PIT offline e suporte explícito a vintages.
- Implementadas transformações autorizadas e comparações descritivas.
- Implementado contexto macro de ativos ex ante e versionado.
- Criados 24 JSON Schemas e fixtures douradas.
- Corrigido o catálogo para não expor séries ainda invisíveis no `decision_time`.
- Corrigido `max_records` para retornar observações mais recentes.
- Corrigido `INDEX_BASE_100` para normalizar cada série por seu primeiro valor observado.
- Adicionados testes de determinismo, leakage, contratos, S21 e integração vertical.

- Isolados schemas em `extension_schemas/` para preservar o registry canônico antigo até S40/P0.
