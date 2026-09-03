# Architecture

## Mission

P4 converts point-in-time facts from P2 and structured interpretation from P3 into auditable, multi-horizon representations for P5. It does not create targets, forecasts, candidates, portfolio weights or P&L.

## Pipeline

| Subphase | Responsibility | Principal outputs |
|---|---|---|
| S1 | Boundary authority | validated P2/P3 bundles, cross-boundary consistency, N+1 proposals |
| S2 | Temporal authority | aligned observations, revision selection, missingness, typed canonical store |
| S3 | Theory-first governance | hypothesis passports, observer validation, approved execution registries |
| S4 | Atomic observations | price, liquidity, risk, cross-asset, options, macro/events, social, fundamentals |
| S5 | Economic perspectives | ten interpretable perspective families |
| S6 | Multi-view fusion | alignment, confirmation/conflict, approved interactions, horizon panel |
| S7 | Causal transformations | fit states, normalization, neutralization, redundancy and structural selection |
| S8 | Representations | chronological folds, PCA/Sparse PCA and optional shared-private encoder |
| S9 | Assurance and handoff | lineage, temporal safety, drift/quality, consumer views, P5 handoff and research ledger |

## Architectural rules

- Contracts and schemas are external authority; module wrappers do not contain business mathematics.
- Source data is never silently corrected, imputed to zero or assigned fabricated timestamps/lineage.
- Every composite feature inherits the maximum `available_at` of its parents.
- S7 selection is structural only. Target-aware selection belongs to P5.
- PCA is the primary compressed representation. The encoder is an optional challenger.
- Failure is explicit through status, reason codes and quality artifacts.
- Artifacts are immutable and content-addressed after construction.

## Source layout

- `boundary/` — P2/P3 validation and N+1 control
- `temporal/` — bitemporal resolution and canonical store
- `observers/` — hypothesis/observer governance and reusable operators
- `atomic/` — modality-specific observations
- `perspectives/` — economic families
- `fusion/` — multi-view alignment, conflicts and interactions
- `s7/`, `s8/`, `s9/` — downstream transformation, representation and assurance domains
- `adapters/` — the only authorized cross-contract projections
- `modules/` — the 49 thin canonical wrappers
- `runtime/` — artifact envelopes, hashing, schemas and shared errors

## Public and internal execution contexts

The public API exposes only `models.ExecutionContext`. Economic S4–S6 and downstream S7–S9 contexts are internal validated projections created by `integrated_runner.py`; they are not alternative public entry points. New integrations must extend the projection functions rather than exposing another context model.

## Two temporal modes

### Snapshot

Records omit `decision_time`. S2 uses the run-level cutoff. This preserves legacy P2/P3 behavior.

### Historical backfill

Records contain `decision_time`. S2 validates the record-specific cutoff and preserves it into all downstream features. This prevents all historical observations from collapsing into one snapshot timestamp.
