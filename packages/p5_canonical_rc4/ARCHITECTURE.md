# Architecture

The release preserves the canonical topology: nine subphases, forty-five module IDs, one module registry, one `PhaseRunner`, one frozen artifact domain and content-addressed storage. Services are internal implementation units, not parallel phase engines.

The runtime flow is:

```text
P4 point-in-time views
→ target-specific offline evidence and sealed evaluation
→ marginal distributions
→ multivariate scenarios and dependence
→ regime/OOD/context
→ calibration and ensemble
→ V2 artifacts + V1 projection
→ P6 handoff
```

Challengers are optional and cannot block the CPU-first baseline. Missing capabilities remain unavailable/degraded and never become synthetic numeric values.
