# Semântica temporal

A P4 distingue obrigatoriamente:

- `event_time`: quando o evento ocorreu;
- `reference_time`: período econômico ao qual o dado se refere;
- `published_at`: quando a fonte publicou;
- `available_at`: quando o pipeline poderia usar a informação;
- `ingested_at`: quando foi capturada;
- `decision_time`: instante simulado de decisão;
- `calculation_time`: quando a feature foi materializada.

Regra central:

```text
available_at <= decision_time
fit_end < calculation_time
```

Dados revisáveis devem manter vintage. Nenhum default temporal pode ser fabricado.
