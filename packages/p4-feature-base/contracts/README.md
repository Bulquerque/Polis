# Contract Authority Map

The contract folders preserve the original domain boundaries while the runtime presents one integrated phase.

| Folder | Authority |
|---|---|
| `foundation/` | S1–S3 boundary, temporal and observer-governance contracts |
| `economic/` | S4–S6 atomic observations, perspectives and multi-view fusion |
| `s7/` | causal transforms, neutralization and structural selection |
| `s8/` | folds, PCA/Sparse PCA and optional encoder representations |
| `s9/` | lineage, drift, quality gates, consumer views and P5 handoff |

Cross-boundary projections are authoritative only in:

- `adapters/foundation_to_economic.py` for S3→S4;
- `adapters/economic_to_transform.py` for S6→S7.

A local module must not bypass these adapters by renaming fields manually.
