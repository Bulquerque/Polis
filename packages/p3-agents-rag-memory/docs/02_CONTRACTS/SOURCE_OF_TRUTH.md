# Contract authority

Authority order:

1. External P0/P2/P4/P9 schemas preserved in `schemas/`.
2. Public internal boundary models in `src/quant_pipeline/phase_03_agents_rag_memory/contracts/`.
3. Generated JSON Schemas in `schemas/integration/`.
4. Module contracts in `contracts/modules/`.
5. Registries in `contracts/` and `schemas/`.
6. Documentation, which explains but does not override executable contracts.

The only public integration pack is `P3_INTEGRATION_CONTRACT_PACK_V2` version `2.0.0`. Old split-package contract packs are not active.

Canonical phase-level files include `INPUT_CONTRACTS.yaml`, `OUTPUT_CONTRACTS.yaml`, `MODULE_IO_MATRIX.yaml` and `INTERNAL_ARTIFACT_REGISTRY.yaml`.
