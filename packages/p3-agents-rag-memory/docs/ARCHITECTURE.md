# Architecture

P3 is one modular package with three layers:

1. `foundation/` prepares time-safe context, population, initial state, knowledge, memory and governed tools.
2. `runtime/`, `runtime_engine/` and subphase packages execute stimuli, activation, cognition, belief updates, social dynamics, memory closure, emergence and output projection.
3. `orchestration/` owns composition, the 81-module registry, the foundation/runtime boundary, cycle execution and diagnostics.

The canonical flow is:

```text
P2 → S1–S16 → FoundationRuntimeManifest V2 → S17–S31
   → P4 outputs + P9 outputs + variable-evolution manifest
   → closure/checkpoint → next cycle
```

The boundary is reference-only. Large artifacts are passed by validated pointers with hashes and lineage rather than copied into manifests.
