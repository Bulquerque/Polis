# Code standards

- Strict typed models at boundaries; immutable domain values where practical.
- Explicit dependency injection; no hidden environment reads in domain logic.
- Fail closed on schema, temporal, authorization or provider errors.
- One canonical registry; no reflection-based discovery.
- No generic `utils.py` or silent `except Exception` success paths.
- External SDK types stay inside adapters.
- Stable module IDs and reference-only cross-capability artifacts.
