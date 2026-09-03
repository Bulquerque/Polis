# Literature Mapping

| Conceito | Módulo | Implementado | Não implementado / limite |
|---|---|---|---|
| State-contingent claims | S5/S6 | target vectors e replication basis | mercado completo não é assumido |
| Static replication | S6 | cash/underlying/options observadas | continuum de strikes ausente |
| Arbitrage-free prices | S1/S5 | diagnóstico e convexidade discreta | calibração SSVI completa ausente |
| Option portfolio optimization | S6 | weighted approximation com budgets | não é alocação de carteira P8 |
| Robust payoff evaluation | S7 | ambiguity alternatives explícitas | DRO contínua ausente |
| Sparse/cardinality constraints | S6 | max legs, quantities e penalties | prova global depende do solver |
| Mixed-integer optimization | S6.M03 | enumeração inteira limitada | MILP general-purpose ausente |
| Multiobjective / QD | S9 | nichos técnicos e representatives | não é ranking econômico |
| Model ambiguity | S7.M07 | worst-case em distribuições fornecidas | ambiguity set não é inventado |
| Deep hedging | fronteira futura P8 | não implementado | gestão dinâmica pertence à P8 |

As técnicas são usadas apenas onde existe implementação e teste correspondente; referências completas ficam na pasta `references/` herdada da fundação.
