# Padrões obrigatórios de código — P4 V14.6-RC1

## Filosofia
Código simples de navegar, tipado nas fronteiras, funcional no núcleo matemático e explícito em I/O, tempo, lineage e erro.

## Organização
- uma pasta por bounded context, não por técnica genérica;
- wrappers em `modules/` são adaptadores finos;
- fórmulas em funções puras;
- orchestration em services;
- filesystem, relógio, encoder e event sink atrás de `Protocol`;
- contratos e schemas não são duplicados em constantes Python.

## Limites
- arquivo ≤350 linhas;
- função ≤60 linhas;
- wrapper ≤40 linhas;
- classe ≤180 linhas;
- nesting ≤4;
- complexidade alvo ≤10;
- no máximo 7 argumentos públicos, usando request object quando necessário.

## Nomes proibidos no core novo
`utils.py`, `helpers.py`, `common.py`, `misc.py`, `base_manager.py`, `do_everything.py`.

## Dataframes
- grain, sort order e dtypes declarados;
- nenhuma dependência semântica de index implícito;
- groupby/rolling sempre precedidos por ordenação determinística;
- cópias evitadas em hot paths, mas nunca à custa de mutação oculta;
- validação na borda, não em cada linha do cálculo.

## Erros
- códigos estáveis;
- catch-all somente na borda;
- causa preservada;
- fail-closed para contrato e temporalidade;
- retry somente para falhas declaradamente transitórias.

## Testes
- unitário por regra;
- oracle numérico por fórmula;
- properties metamórficas;
- fixtures temporais adversariais;
- replay determinístico;
- mini-run por subfase;
- contract tests entre agentes;
- integração P2/P3→P4→P5.


Consulte `P0_P4_CODE_QUALITY_CLOSURE.md` para a auditoria comparativa.
