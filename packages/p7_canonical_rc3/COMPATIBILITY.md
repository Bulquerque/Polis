# P5 V2/RC34 and P6 RC6.2 compatibility

P7 2.3.1rc3 accepts two upstream wire formats at its S1 boundary:

1. the canonical P7 handoff contract; and
2. the native `phase7_strategy_handoff_manifest` published by P6 RC6.2.

The native conversion is isolated in `foundation/compatibility/`. The adapter validates the original P6 artifact hashes and manifest references before it creates canonical P7 artifacts. S2-S8 therefore continue to use one internal representation.

## P5 provenance

P7 does not reinterpret P5 forecasts directly. P5 RC34 provenance is received through the P6 market snapshot and P5 compatibility report. The compatibility receipt records:

- P5 manifest ID and SHA-256;
- whether P6 consumed the full P5 manifest;
- the number of P5 source artifacts;
- the original P6 manifest ID and SHA-256.

## Normalizations performed at S1

- P6 `horizon_days` becomes a structured calendar-day horizon such as `30_calendar_days`.
- Canonical decimal strings are parsed only for declared numeric fields; booleans, non-finite values, and free-form strings are rejected or remain unavailable.
- Defined-risk evidence is taken from P6 qualification records or derived only when the published payoff reconciles maximum loss and proves a bounded right tail.
- Entry cost is mapped from P6 conservative entry cost with its method preserved.
- Liquidity uses an explicit transformation of published relative spread. Raw weakest-leg liquidity remains separately identified and is not mislabeled as a normalized score.
- P6 publication timestamps are not treated as source-event availability. The normalized boundary uses the P6-validated decision anchor and retains the original manifest identity in lineage.
- Candidate equivalence records are filtered to candidates actually published to P7.
- Research artifacts whose grain is not candidate-level are excluded from the runtime handoff rather than coerced.

No missing calendar, margin confidence, liquidity, OOD evidence, or score confidence is manufactured.

## Empty-valid behavior

When P6 publishes candidates but every candidate is blocked by P7 eligibility, P7 returns `EMPTY_VALID`. The release receipt conserves the upstream population as eligibility-blocked and publishes an empty P8 handoff. The tournament, runtime learning, and ranking stages are skipped because there is no valid comparison universe.

## Packaging

P7 does not ship `quant_pipeline/__init__.py`; it participates in the shared namespace without claiming ownership of the root package. P5, P6, and P7 wheels were installed in one transaction and imported successfully from the same site-packages directory.

P5, P6 and P7 participate in the same implicit `quant_pipeline` namespace. Source composition and wheel installation were validated without a root-package owner.
