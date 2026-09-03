# Integration Guide

## Reconciled boundary S3→S4

S2 keeps the rich typed canonical observation representation:

- `value_type`
- typed value fields
- source artifact/record identity
- source dimensions
- temporal and missingness states
- lineage

`adapters/foundation_to_economic.py` projects this into the narrow numeric contract consumed by S4 while preserving rich fields in `attributes`. It also compiles S3-approved hypotheses into atomic execution specifications. Derived output feature IDs are resolved to executable observer IDs without changing their final feature identity.

## Reconciled boundary S6→S7

`adapters/economic_to_transform.py` creates the canonical horizon record used by S7. It preserves:

- `feature_value`
- family, phenomenon and perspective IDs
- parameterization and horizon
- exact `available_at`
- source modalities and parent feature IDs
- implementation tier and compute metadata
- lineage and quality/missingness state

For interactions, conflict measures and other composites, `available_at` is the latest parent availability, never an artificial zero-age timestamp.

## P2/P3 compatibility

S1 accepts the RC4.1 handoff shape in compatibility mode, validates the declared hashes/manifests and emits capability matrices. Optional upstream capabilities remain explicit as `UNAVAILABLE_UPSTREAM`; they are not fabricated.

## P5 compatibility

S9 produces the eight legacy P4 outputs plus typed consumer views and a quality decision. P5 handoff creation is blocked when family coverage, temporal safety or representation quality does not meet policy. A blocked handoff is a valid controlled result, not a crashed run.

## Change control

Changes to any of these require a contract revision and migration note:

- artifact grain or required fields;
- producer module identity;
- quality/missingness/execution status vocabulary;
- temporal derivation rules;
- feature IDs or hypothesis IDs;
- cross-phase inputs/outputs.

Do not add a second adapter or second artifact envelope to solve a local issue. Extend the canonical adapter/runtime instead.
