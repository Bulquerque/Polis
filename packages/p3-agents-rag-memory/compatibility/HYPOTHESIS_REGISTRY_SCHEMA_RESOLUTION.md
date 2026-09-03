# Hypothesis registry schema resolution

The sanitized repository contains different copies of `hypothesis_registry.schema.yaml`. This P3 release uses the schema owned by the actual Phase 4 consumer because P3.S30 produces this artifact for P4. The richer internal P3 semantic schema remains in `schemas/products/s30/hypothesis_registry.semantic.schema.json`. Full-repository integration must update the global mirror to the same consumer-compatible schema and regenerate its hash evidence.
