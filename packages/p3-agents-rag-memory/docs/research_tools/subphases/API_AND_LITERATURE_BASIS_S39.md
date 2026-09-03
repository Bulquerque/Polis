# API and Literature Basis — P3.S39

## API decisions

### Python 3.13 standard library

The implementation uses `math`, `statistics`, `random.Random`, `collections`,
`itertools` and dataclasses. The P3 package already requires Python 3.13. The
seeded resampling code creates a local `random.Random` instance; it does not use
global random state.

The standard-library `statistics` module is appropriate here because P3.S39 is
a small diagnostic layer rather than a full statistical computing platform.
Every convention not fixed by the library, including `ddof`, annualization,
alignment, discretization and resampling, is explicit in code and configuration.

### NumPy, SciPy and arch

The official NumPy and SciPy projects were reviewed for correlation, rank
correlation, quantiles and bootstrap API conventions. The `arch` repository was
reviewed for its explicit IID, moving-block, circular-block and stationary
bootstrap separation. These libraries are not imported by the patch, avoiding
new mandatory binary dependencies and version coupling.

## Literature applied

### Realized and range volatility

- Andersen, Bollerslev, Diebold and Labys, *Modeling and Forecasting Realized
  Volatility*.
- Parkinson, *The Extreme Value Method for Estimating the Variance of the Rate
  of Return* (1980).
- Garman and Klass, *On the Estimation of Security Price Volatilities from
  Historical Data* (1980).

Application: estimators remain separately named, assumptions are explicit and
no estimator is selected from its realized result.

### Bootstrap

- Efron, *Bootstrap Methods: Another Look at the Jackknife* (1979).

Application: resampling is seeded, bounded and reported. Because financial
series can be dependent, stability diagnostics use moving blocks rather than an
unqualified IID bootstrap.

### Information measures

- Shannon, *A Mathematical Theory of Communication* (1948).
- Bandt and Pompe, *Permutation Entropy: A Natural Complexity Measure for Time
  Series* (2002).

Application: Shannon entropy uses a frozen symbolization policy. Permutation
entropy uses ordinal patterns with explicit embedding and delay. Ties are
reported and resolved deterministically.

### Event studies

- MacKinlay, *Event Studies in Economics and Finance* (1997).

Application: event windows support benchmark-adjusted descriptive returns but
never claim causality. Events and complete windows must be observable before the
operation executes.

## Deliberate exclusions

The patch does not implement:

- statistical hypothesis testing or p-value selection;
- automatic lag, window, estimator or bin optimization;
- volatility forecasting models;
- GARCH, HMM or regime inference;
- backtesting;
- signal or portfolio construction.

Those responsibilities belong to later phases and require separate contracts.
