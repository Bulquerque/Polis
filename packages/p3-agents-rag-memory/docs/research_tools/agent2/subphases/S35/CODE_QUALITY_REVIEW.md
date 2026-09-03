# Revisão de qualidade do código

## Resultado

A implementação segue contratos estritos, composição explícita, handlers read-only, dependências por portas e nenhuma rede obrigatória. O relatório mecanicamente gerado está em `QUALITY_REPORT.json`.

## Verificações realizadas

- compilação de todos os arquivos Python;
- parsing AST;
- busca por relógio de parede, rede direta, wildcard imports, TODO/FIXME e dependências downstream proibidas;
- teste AST das fronteiras arquiteturais;
- busca de duplicatas exatas;
- contratos Pydantic com campos extras proibidos;
- 85% de cobertura total com branches;
- testes de point-in-time, replay, hashes, fallback, proveniência e qualificação.

## Tamanho e navegação

Os wrappers canônicos mantêm somente adaptação de input/output. A lógica está dividida por significado em snapshot, retrieval, proveniência, handlers, contratos e qualificação.

Alguns métodos de orquestração permanecem acima do alvo preferencial de 30 linhas porque descrevem sequências lineares de validação ou montagem. Eles foram revisados e não escondem transporte, I/O ou estado global. O pipeline principal de ranking foi separado em helpers de:

- scoring lexical e semântico;
- fusão;
- reranking;
- montagem dos hits.

Esses limites são gatilhos de revisão, não incentivos para fragmentar código simples em abstrações artificiais.

## Limitação das ferramentas do ambiente

`ruff` e `mypy` não estavam instalados. Em substituição, o pacote usa compilação, testes AST, contratos estritos, schemas gerados, testes de consumidor e cobertura de branches. A execução futura em CI deve acrescentar `ruff` e `mypy --strict` sem mudar os contratos.
