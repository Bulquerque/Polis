# Internal compatibility — RC34

RC34 preserves all 45 canonical module IDs, the single registry, the single `PhaseRunner`, canonical artifact names and generated wrapper contracts. The hardening changes update existing handlers and services rather than adding a parallel phase engine.

V1 publication remains a compatibility projection. The P6-native `market_belief_state` is validated against P6 RC6.0-C. Extended V2 artifacts remain canonical P5 outputs, while full eleven-reference manifest consumption is explicitly pending a P6 consumer update. P7 consumes evaluated P6 candidates and has no direct P5 adapter.
