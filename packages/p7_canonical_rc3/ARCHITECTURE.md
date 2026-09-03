# P7 sequential architecture

## Phase topology

```text
P6
 |
 v
S1 Boundary and Temporal Integrity
 |
 v
S2 Eligibility and Comparability
 |
 v
S3 Dominance, Pareto and Factor Adjustment
 |
 v
S4 Interpretable Multi-Head Scoring
 |                         \
 |                          -> S5 Offline LTR Training and Qualification
 |                                      |
 |                                      v
 +-------------------------------> S6 Runtime Scoring and Hybrid Blend
                                           |
                                           v
                              S7 Diversity, Safety and Abstention
                                           |
                                           v
                                  S8 Ranking and P8 Publication
                                           |
                                           v
                                           P8
```

S5 is offline-only. A model may enter S6 only through a versioned, promoted model artifact whose training cutoff precedes the decision time.


## Upstream compatibility boundary

S1 accepts the canonical P7 contract and the native P6 RC6.1 publication. Native artifacts are hash-validated in their original wire format, normalized once, and then passed through the ordinary S1 validator. The rest of the phase has no P6-specific branches. P5 RC34 provenance is carried through P6 receipts and market-snapshot references; P7 does not recompute P5 beliefs.

If S2 produces zero eligible candidates, the phase uses a fail-closed empty-valid closure. S3-S7 are skipped, S8 publishes empty ranked/abstained outputs, and the release receipt conserves all upstream candidates as eligibility-blocked.

## Internal layers

Each subphase follows the same direction of dependency:

```text
module wrapper -> application service -> domain policy -> boundary model / port
```

The phase runner orchestrates modules but contains no ranking mathematics. Cross-subphase communication occurs only through content-addressed artifacts validated by transition contracts.

## Canonical boundaries

1. `foundation_to_tournament_handoff_manifest`
2. `tournament_to_learning_handoff_manifest`
3. `learning_to_finalization_handoff_manifest`
4. `phase8_strategy_ranking_handoff_manifest`

Transitions normalize schemas only. They may not create economic facts, infer missing confidence, fabricate OOD evidence, reconstruct P6 instruments or change candidate eligibility.

## Candidate conservation

Every P6 candidate must terminate exactly once as one of:

- boundary rejected;
- temporally rejected;
- eligibility blocked;
- dominated;
- safety blocked;
- abstained;
- ranked.

The release publisher verifies conservation and hashes the final P8 references.

## Compatibility

P6 and P8 compatibility adapters may exist only at the public phase boundaries. The P7 core has one canonical representation for candidates, metrics, scores, manifests and reason codes.
