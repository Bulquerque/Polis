# P0.S1 — Architecture Registry & Source of Truth

## Purpose

P0.S1 is the architecture authority adapter for Phase 0. It does not create economic data and does not decide trades. Its responsibility is to prove, in sequence, that the declared project inventory and topology correspond to the authorized architecture baseline.

The public module IDs and contracts remain unchanged:

1. `P0.S1.M01` — phase registry loader
2. `P0.S1.M02` — subphase registry loader
3. `P0.S1.M03` — module registry loader
4. `P0.S1.M04` — connection matrix validator
5. `P0.S1.M05` — forbidden connection detector

## Reformed architecture

```text
ARCHITECTURE_BASELINE.yaml
        |
        v
M01 Phase Registry
        |
        v
M02 Subphase Registry
        |
        v
M03 Module Registry + Contract Binding
        |
        v
M04 Topology Validation
        |
        v
M05 Declarative Architecture Policy Engine
```

### M01 — phase registry authority

Validates phase identity, package identity, execution plane, release binding and architecture authority. Release-specific expectations are read from the versioned architecture baseline rather than duplicated as Python constants.

### M02 — subphase hierarchy

Validates the complete phase→subphase hierarchy, registry provenance and source hashes. Counts and exact subphase IDs are supplied by the architecture baseline.

### M03 — module inventory

Validates module identity, parent phase/subphase, canonical contract path, contract YAML identity and SHA-256 binding. The expected module count and IDs are baseline data, not code literals.

### M04 — topology validator

Validates structure only:

- matrix identity and format;
- phase coverage;
- module identities;
- reciprocal dependencies;
- artifact producer/consumer consistency;
- unique producers;
- zero-trust artifact class restrictions.

It no longer owns forbidden-connection policy semantics.

### M05 — policy engine

Applies declarative architecture policy to an already materialized topology. The legacy `forbidden_connections` surface remains accepted, while `policy_rules` provides structured selectors by phase and plane.

M05 reports findings; it does not stop development or modify another phase. A blocking finding means the relevant phase/release is not ready for qualification or release.

## Internal clean-code boundaries

Public module files remain stable. Shared implementation is split into focused internal modules:

- `_p0_s1_common.py` — YAML/schema/hash/time/boundary helpers;
- `_p0_s1_baseline.py` — architecture baseline access;
- `_p0_s1_registry_attestation.py` — upstream registry attestation;
- `_p0_s1_topology.py` — phase-local topology validation;
- `_p0_s1_global_topology.py` — global P0–P9 topology index;
- `_p0_s1_policy.py` — declarative forbidden-connection policy;
- `_p0_s1_artifacts.py` — explicit artifact classification.

The reform enforces the project Clean Code limits for P0.S1:

- Python file <= 350 lines;
- function <= 60 lines;
- line length <= 120 characters;
- no P0.S1 public module imports private helpers from another P0.S1 public module.

## Compatibility

The public `run_module(inputs, config=None)` contract is preserved for M01–M05.

Deprecated helper aliases remain exported from M01 temporarily because later P0 subphases in the current RC4.1 package still import them. New S1 code does not use those private cross-module imports. They can be migrated when S2/S3/S5/S6 are reformed.

## Source-of-truth policy

`source_of_truth/architecture/ARCHITECTURE_BASELINE.yaml` is the versioned operational baseline consumed by P0.S1. It materializes release-specific expectations (10 phases, 54 subphases and 166 modules for RC4.1) outside Python code.

It is a P0.S1 operational binding of the global source of truth, not an independent competing architecture authority.
