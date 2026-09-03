# Architecture

```text
P5 belief bundle + P2 PIT market
    → S1 boundary and immutable snapshot
    → S2 canonical strategy domain
    → S3 template generation
    → S4 bounded mutation
    → S5 target payoff and market-implied diagnostics
    → S6 inverse design solver portfolio
    → S7 pricing, Greeks, nominal/pathwise/ambiguity evaluation
    → S8 feasibility and defined-risk proof
    → S9 canonicalization, equivalence and quality-diversity
    → S10 qualification and P7 publication
```

## Dependency rules

- `foundation/` owns envelope, hashes, configuration, errors and results.
- `domain/` owns the only canonical market, strategy, evaluation and synthesis models.
- subphases may consume upstream public artifacts; they do not import another subphase's private runner internals.
- compatibility is isolated under `boundaries/` and S10 projections.
- `TEMPLATE_ONLY` never depends on successful mutation or solver execution.

## Status semantics

Artifact production status (`COMPLETE`, `DEGRADED`, `EMPTY_VALID`, `BLOCKED`, `ERROR`) is separate from economic qualification. Missing values remain null with reason codes; no economic absence is silently converted to zero.
