# Cross-Phase Compatibility Matrix

## P0 — authority, qualification and promotion

P0 remains the global authority for module identity, manifests, hashes, promotion status and cross-phase topology. P4 does not rewrite the global registry. The final integrator must register:

- release `V14.9-RC1`;
- nine P4 subphases and 49 canonical modules;
- the canonical P4 source root;
- the P2/P3 inputs and P5 outputs listed in the frozen contracts;
- qualification evidence and the release manifest.

P4 treats a P0 registration mismatch as an integration problem, not as a reason to weaken local validation.

## P1 — acquisition

P4 has no direct P1 dependency. P1 evidence must reach P4 only after P2 has normalized, versioned and qualified it. Direct P1 imports, API calls or raw-provider payloads are forbidden inside P4.

## P2 — point-in-time fact authority

Supported compatibility mode: `RC4_1`.

The canonical P4 module inventory is 49 modules. The package also carries one
provenance-backed import alias, `P4_S1_M01_phase2_feature_intake_validator`,
for frozen RC4.1 callers. The alias is included in the file manifest but is
excluded from `MODULE_CATALOG.csv`, the contract matrix, and every canonical
module count. Its provenance is declared in `contracts/CONTRACT_AUTHORITY.yaml`.

P4 validates P2 handoff references and then preserves:

- source and record identity;
- revisions and vintages;
- `available_at` and record-specific `decision_time`;
- missingness and upstream capability states;
- corporate-action and calendar alignment.

Optional P2 capabilities such as fundamentals, options or term structures remain explicit as unavailable when absent. They are never fabricated.

## P3 — interpretation, evidence and N+1 proposals

P4 consumes the structured social/evidence handoff without flattening disagreement, evidence quality, memory and hypotheses into one score. The optional variable-evolution manifest is accepted only from an authorized prior cycle and remains a pending proposal; it cannot modify the active observer registry in the same run.

## P5 — predictive consumer

P4 delivers state representations, not labels or forecasts. The handoff contains:

- interpretable and structurally selected matrices;
- PCA/Sparse-PCA factors;
- an optional encoder artifact with explicit skip status when not authorized;
- lineage, drift and representation-quality reports;
- consumer views and the P5 handoff manifest.

Target-aware feature selection, supervised representation learning and alpha qualification belong to P5. Production promotion requires a formal P5 receipt implementation.

## P6–P8 — downstream indirect compatibility

P4 does not create candidate IDs, option legs, ranking scores, portfolio weights, execution decisions or P&L. These phases consume P4 only indirectly through P5 and later contracts. Forbidden-field scans protect this boundary.

## P9 — evaluation and next-cycle learning

P9 results cannot modify P4 within the evaluated cycle. A new feature idea must flow through the controlled next-cycle path:

```text
P9 evaluation → P3 hypothesis/retro process → N+1 proposal → P4 review in a later cycle
```

The P4 research ledger preserves all authorized attempts and negative results so P9 can account for multiple testing and selection.
