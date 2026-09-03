# Architecture

## End-to-end flow

```text
Provider adapters
      ↓
Raw ingestion and lineage
      ↓
Point-in-time quality and harmonization
      ↓
Governed context, retrieval and memory
      ↓
Feature representation and fold construction
      ↓
Forecasts and candidate generation
      ↓
Deterministic ranking
      ↓
Portfolio sizing, risk and backtest ledger
      ↓
Robustness, attribution and next-cycle learning
```

Each phase owns its input/output contracts and keeps package-specific code, schemas and tests close to the implementation. Cross-phase handoffs are represented by explicit schemas and manifests rather than implicit global state.

## Design principles

1. **Point-in-time first** — data availability is evaluated against the decision timestamp; future observations must not enter a historical feature or signal.
2. **Lineage by default** — provider identity, request context, content hashes and version information travel with captured inputs.
3. **Fail-closed boundaries** — malformed, ambiguous or temporally invalid inputs are rejected at the boundary where they enter the pipeline.
4. **Deterministic research** — ranking, portfolio decisions and replayable transformations use explicit ordering and versioned parameters.
5. **Research scope** — the code models observed marks and explicit transaction costs; live execution and economic promotion are separate concerns.

## Package boundaries

- `p0-zero-trust` defines governance, contracts and integrity rules.
- `p1-ingestion` captures and versions source material.
- `p2-quality-pit` checks quality, harmonization and temporal eligibility.
- `p3-agents-rag-memory` manages context, retrieval, tools and memory.
- `p4-feature-base` creates point-in-time features and folds.
- `p5_canonical_rc4` produces forecasts for research workflows.
- `p6_canonical_rc4` transforms forecasts into eligible candidates.
- `p7_canonical_rc3` applies filters, scores and deterministic ranking.
- `p8_integrated_rc3` models sizing, risk, costs and ledger outcomes.
- `p9_canonical_unified_rc4` measures robustness and feeds the next research cycle.
