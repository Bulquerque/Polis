# Source of Truth — P4 V14.9-RC1

This release has one canonical implementation tree:

```text
src/quant_pipeline/phase_04_feature_base/
```

Generated wheels, build directories, caches and source snapshots from individual workstreams are not part of the product tree.

## Authority order

The canonical point-in-time policy is inherited from
`global_contracts_parallel_agents/v14_1_global_contracts_parallel_agents_RC4_1/POINT_IN_TIME_AI_POLICY.md`.

1. Runtime models and artifact envelope:
   - `src/quant_pipeline/phase_04_feature_base/models.py`
   - `src/quant_pipeline/phase_04_feature_base/runtime/`
2. Cross-subphase integration:
   - `src/quant_pipeline/phase_04_feature_base/integrated_runner.py`
   - `src/quant_pipeline/phase_04_feature_base/adapters/`
3. Boundary contracts:
   - `contracts/`
   - `schemas/`
4. Research and feature authority:
   - `registries/foundation/`
   - `registries/economic/`
5. Public API:
   - `src/quant_pipeline/phase_04_feature_base/__init__.py`
6. Integrated regression:
   - `tests/test_integrated_pipeline.py`

## Contract generations

The integrated release version is `V14.9-RC1`. All newly generated P4 artifact schemas use `v14.9-rc1`. Upstream P2/P3 schemas may retain RC4.1 identifiers when processed through the explicit compatibility adapter; those identifiers describe upstream schema generations, not the P4 package version.

## Change rule

Do not introduce a second artifact envelope, second canonical observation model or second S6→S7 adapter. Extend the canonical implementation and add a migration note instead.
