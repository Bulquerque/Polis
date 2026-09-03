# Debugging runbook

## Trace order

Start from the failing artifact and follow:

```text
artifact_id → producer_module_id → module receipt → input artifact IDs → content hashes → source record lineage
```

## Runtime checkpoints

1. **S1:** manifest/hash mismatch, orphan records, future evidence or forbidden fields.
2. **S2:** eligibility reason codes, comparison-group coverage and metric semantics.
3. **S3:** dominance relations, factor-adjustment evidence and Pareto layer.
4. **S4:** head inputs, contribution reconciliation and interpretable score.
5. **S6:** model qualification, cutoff compatibility, calibration and fallback mode.
6. **S7:** similarity edges, diversity adjustment, safety reasons and abstention.
7. **S8:** group ordering, tie trace, thesis evidence and execution-context references.

## Fail-closed rules

- Never replace absence with zero.
- Never relax `available_at <= decision_time`.
- Never reconstruct P6 price, payoff, Greeks, margin, cost or liquidity in P7.
- Never train during runtime.
- Never rank a candidate that failed safety or rankability.

## Reproduction

Use the exact input hashes, configuration, seed, pipeline version and timestamps recorded in the module receipt. Run with `PYTHONDONTWRITEBYTECODE=1` and a clean extracted package.
