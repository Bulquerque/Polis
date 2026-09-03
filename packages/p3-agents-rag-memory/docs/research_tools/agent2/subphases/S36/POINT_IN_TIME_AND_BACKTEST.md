# Point-in-Time and Backtest

## Regras

```text
market row: available_at <= decision_time
corporate action: available_at <= decision_time
option contract: first_seen_date <= decision_date
option quote: available_at <= decision_time
```

A filtragem ocorre antes de seleção do snapshot, agregação, comparação ou diagnóstico.

## Campos temporais

- `date`: referência da observação;
- `available_at`: quando a informação podia ser conhecida;
- `first_seen_date`: primeira visibilidade do contrato;
- `expiration_date`: validade econômica do contrato;
- `announcement_date`: anúncio de ação corporativa;
- `decision_time`: instante histórico injetado pelo runtime.

## Invariantes testadas

- adicionar linha futura não altera registros históricos retornados;
- antecipar `decision_time` não aumenta visibilidade;
- reordenar input não muda resultado ou hash;
- contrato e quote futuros não entram na cadeia histórica;
- ações não anunciadas são rejeitadas;
- dados sem timestamp de visibilidade são rejeitados.

## Rede

A V1 não faz chamadas HTTP. Backtest opera apenas sobre snapshots congelados e ports locais.
