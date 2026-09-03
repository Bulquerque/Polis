# Contratos internos

Os contratos internos são definidos por:
- `contracts/MODULE_IO_MATRIX.yaml`;
- `contracts/INTERNAL_ARTIFACT_BUNDLES.yaml`;
- `contracts/ARTIFACT_ENVELOPE_STANDARD.yaml`;
- YAML individual de cada módulo;
- schemas dos artefatos.

Bundles são aliases de dependência, não payloads copiados. Cada artefato possui um único produtor. Outputs opcionais são emitidos com status explícito, nunca omitidos silenciosamente.
