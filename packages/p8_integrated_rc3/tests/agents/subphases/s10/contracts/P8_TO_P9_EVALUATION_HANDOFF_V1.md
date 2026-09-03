# P8_TO_P9_EVALUATION_HANDOFF_V1

A P8 publica evidência; a P9 realiza atribuição, aprendizagem e recomendação de promoção.

## Classes epistêmicas

- `FACTUAL_EXECUTED`
- `FACTUAL_OBSERVED_NOT_EXECUTED`
- `OBSERVABLE_COUNTERFACTUAL`
- `MODEL_BASED_COUNTERFACTUAL`
- `CENSORED`
- `UNOBSERVABLE`

`UNAVAILABLE` é estado de disponibilidade e não substitui `UNOBSERVABLE`.

## Evaluation commitment

O commitment deve ser criado no máximo em `decision_time` e contém outcome definition, horizons, metrics, benchmarks, policy hashes e holdout constraints. A P8 fornece maturity hints; a P9 decide a maturidade efetiva.

## Lineage mínimo

`P4 view → P5 belief → P6 candidate → P7 decision → P8 decision → order → fill → position → outcome evidence`.
