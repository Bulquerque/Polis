# Gates de qualidade

## Gate estrutural

- 70 IDs de módulo únicos;
- 10 subfases;
- nenhum path de runtime duplicado;
- nenhum `quant_pipeline/__init__.py` regular;
- sem bytecode, caches ou artefatos temporários na release.

## Gate contratual

- extras proibidos nas fronteiras estritas;
- clocks timezone-aware;
- hashes validados onde fazem parte do contrato;
- receipts e terminal states reconciliados;
- ausência e evidência insuficiente permanecem explícitas.

## Gate funcional

- testes unitários;
- contratos e schemas;
- numerical reference tests;
- property/metamorphic tests;
- replay determinístico;
- adversarial/fail-closed;
- integração entre subfases;
- golden threads de promoção, abstention e rollback.

## Gate de empacotamento

- extração limpa;
- AST, JSON e YAML válidos;
- import sweep de todos os módulos;
- manifest SHA-256;
- nenhuma referência administrativa proibida.
