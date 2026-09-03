# Package guide

The package tree keeps implementation, contracts, schemas and tests close to each phase boundary.

| Package | Main responsibility | Typical entry point |
| --- | --- | --- |
| `packages/p0-zero-trust` | Governance and integrity | Package README and tests |
| `packages/p1-ingestion` | Ingestion, inventory and versioning | Package README and tests |
| `packages/p2-quality-pit` | Quality and point-in-time rules | Package README and tests |
| `packages/p3-agents-rag-memory` | Agents, retrieval, memory and tools | `p3` when installed |
| `packages/p4-feature-base` | Feature representation and folds | Package README and tests |
| `packages/p5_canonical_rc4` | Underlying forecasts | `p5` when installed |
| `packages/p6_canonical_rc4` | Strategy synthesis and candidates | `p6` when installed |
| `packages/p7_canonical_rc3` | Strategy tournament and ranking | Package README and tests |
| `packages/p8_integrated_rc3` | Portfolio control and backtest | Package README and tests |
| `packages/p9_canonical_unified_rc4` | Robustness, evaluation and learning | Package README and tests |

For provider-backed runs, configure credentials outside the repository and use the package's documented command. No credential values or private data belong in source control.
