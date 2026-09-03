# Engineering standard

## Dependency direction

```text
module wrapper → application service → domain policy → boundary model or port
```

No downstream area imports a private implementation from an upstream area. Cross-subphase communication uses immutable, content-addressed artifacts.

## Hard limits

- Python file: 350 lines.
- Function: 60 lines.
- Module wrapper: 80 lines.
- Class: 180 lines.
- Broad `Exception` or `BaseException` catches: forbidden.
- NaN and infinity on the wire: forbidden.

## Code rules

- Public wrappers keep `run_module(inputs, config)`.
- Convert mappings to typed models at the boundary.
- No global mutable state.
- No dynamic module discovery.
- No economic defaults.
- No duplicate canonical models.
- Deterministic serialization, IDs and ranking.
- Missing capability is represented as unavailable, degraded or abstained.

## Tests

Tests cover domain policies, module behavior, contracts, subphase integration, internal handoffs, temporal invariants, adversarial inputs, deterministic replay and the complete P6→P7→P8 route.
