# P3.S33 Point-in-Time and Provenance Contract

## Modelo temporal

A extensão preserva dimensões distintas:

```text
event_time       evento econômico
period_end       período representado
published_at     publicação formal
available_at     instante em que o sistema poderia conhecer o dado
ingested_at      captura na P1
decision_time    instante histórico congelado da simulação
```

A autoridade de visibilidade é `available_at`. Datas econômicas ou períodos de referência não substituem esse campo.

## Vintages

Políticas suportadas:

- `KNOWN_AT_DECISION_TIME`
- `ORIGINAL_RELEASE`
- `LATEST_KNOWN_AT_DECISION_TIME`

`LATEST_REVISED_TODAY` é proibida em backtest. A modelagem segue o princípio oficial do FRED/ALFRED de consultar observações como existiam em datas históricas específicas.

## Proveniência

A cadeia é representada como:

```text
P1 source snapshot
→ P1 raw artifact reference
→ P2 semantic artifact/record
→ P3 authorized query
→ tool evidence
```

O desenho é compatível conceitualmente com PROV-O (`Entity`, `Activity`, `Agent`) e com o modelo OpenLineage de datasets, jobs e runs, mas não adiciona dependência obrigatória ou backend externo.

## Fail-closed

- registro observacional sem `available_at`: bloqueado;
- reference data temporal sem intervalo de vigência: bloqueado;
- path com traversal: rejeitado;
- hash P1 inconsistente: bloqueado;
- raw artifact sem vínculo P2: órfão não autorizado;
- `request.as_of != decision_time`: rejeitado;
- datetime sem timezone: rejeitado.
