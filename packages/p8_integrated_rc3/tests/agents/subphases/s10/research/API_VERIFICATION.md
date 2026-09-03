# API and standards verification

Verificado em 2026-08-03:

- Pydantic v2.13: strict/frozen models, `extra="forbid"`, `model_validate_json` e JSON Schema generation.
- JSON Schema Draft 2020-12: schemas públicos fechados.
- Python Packaging User Guide: `src/` layout e native namespace packages.
- pytest 9: fixtures e parametrization.
- W3C PROV-O: lineage/provenance interoperável.
- Microsoft Event Sourcing Pattern: event log append-only como authority e replay para reidratação.
- Reproducible Builds `SOURCE_DATE_EPOCH`: epoch fixo em builds repetidos.
- CycloneDX 1.6: SBOM de componentes e dependências.

Não há calls de rede, broker ou market data no runtime da S10.
