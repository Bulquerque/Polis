# API and standards verification

Validated against the documentation available on 2026-08-03:

- Pydantic v2.13 documentation and installed version 2.13.4: strict/frozen models, `extra="forbid"`, validation and JSON Schema generation.
- JSON Schema Draft 2020-12 official meta-schema and validation rules.
- Python Packaging User Guide: `src/` layout and native namespace packages.
- pytest 9 documentation: fixtures and parametrized tests.

Design references, not runtime dependencies:

- Black-Box Simplex Architecture for Runtime Assurance.
- Fallback-Safe MPC.
- River and Frouros drift-detection repositories.

The package does not call external APIs and has no broker, market-data or network dependency.
