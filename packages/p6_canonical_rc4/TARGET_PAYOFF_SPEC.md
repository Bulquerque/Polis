# Target Payoff Specification

Modos implementados: `SCENARIO_WEIGHTED`, `TAIL_HEDGE`, `RANGE_EXPRESSION`, `EXPECTED_UTILITY` e `BELIEF_RATIO` condicionado à disponibilidade de estado implícito.

O estado físico da P5 e o diagnóstico risk-neutral permanecem separados. `BELIEF_RATIO` é fail-closed quando não há ao menos três calls utilizáveis, convexidade discreta não negativa ou cobertura suficiente. Targets passam por clipping, smoothing, normalização, confidence shrinkage e qualification de finitude/boundedness.

Limitações: a densidade implícita é um diagnóstico discreto de convexidade de calls, não uma superfície calibrada de produção nem uma estimativa completa de caudas.
