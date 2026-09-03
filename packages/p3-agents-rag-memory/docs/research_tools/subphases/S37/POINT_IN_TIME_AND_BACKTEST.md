# Point-in-time e backtest

## Regra

```text
available_at <= decision_time
```

## Vintage

- `ORIGINAL_RELEASE`: primeira versão conhecida de cada observação.
- `LATEST_KNOWN_AT_DECISION_TIME`: versão mais recente já disponível no instante.
- `KNOWN_AT_DECISION_TIME`: política padrão para observação histórica.

O valor revisado hoje nunca substitui retroativamente o valor conhecido na simulação.

## Ordem operacional

```text
snapshot autorizado
→ validação de available_at
→ seleção de vintage
→ filtro de datas
→ transformação
→ comparação
→ evidência e PIT proof
```

## Propriedades testadas

- antecipar `decision_time` não aumenta visibilidade;
- adicionar registro futuro não muda resultado passado;
- reordenar linhas não muda o hash;
- série exclusivamente futura não aparece na busca;
- contexto macro futuro é rejeitado.
