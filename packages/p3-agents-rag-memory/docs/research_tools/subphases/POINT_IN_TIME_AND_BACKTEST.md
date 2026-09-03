# Point-in-time e backtest

## Regra central

```text
record.available_at <= decision_time <= corpus_snapshot.as_of_time
```

O snapshot pode conter registros posteriores ao `decision_time` de uma consulta histórica, mas eles são removidos antes de:

- tokenização para BM25;
- cálculo de document frequency;
- recuperação densa;
- RRF;
- reranking;
- montagem de documentos;
- comparação de versões;
- timeline.

Assim, até o IDF do BM25 é calculado apenas no corpus visível.

## Provas

Cada resultado contém:

- registros examinados;
- registros visíveis;
- registros rejeitados por futuro;
- registros rejeitados por filtro;
- primeiro e último `available_at`;
- snapshot;
- hashes de inputs;
- hash da prova.

## Invariantes testadas

- adicionar um chunk futuro não altera o resultado histórico;
- reduzir `decision_time` não aumenta visibilidade;
- reordenar o corpus não altera ranking;
- conteúdo duplicado não aparece duas vezes;
- decisão após o snapshot é rejeitada;
- hash adulterado bloqueia carregamento.

## Backtest

- sem rede;
- sem índice live;
- sem download de modelo;
- sem relógio de parede no domínio;
- sem caminhos fornecidos pelo agente;
- sem fallback silencioso;
- sem seleção de estratégia ou modelo.
