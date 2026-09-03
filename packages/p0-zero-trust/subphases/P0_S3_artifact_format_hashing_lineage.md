# P0.S3 — Artifact Format, Hashing & Lineage

## Função

A P0.S3 é a camada de integridade material do Zero Trust. Ela prova quatro propriedades diferentes e complementares sem tocar no fluxo econômico:

1. **P0.S3.M01 — Hash Policy Enforcer:** autentica o conteúdo atual byte a byte.
2. **P0.S3.M02 — Lineage Integrity Checker:** prova a proveniência estrutural e, quando disponível, a linhagem material de runtime.
3. **P0.S3.M03 — Artifact Manifest Auditor:** reconcilia manifesto, registry, filesystem, hashes e lineage para provar a integridade do snapshot atual.
4. **P0.S3.M04 — Artifact Immutability Checker:** compara snapshots/releases para detectar adulteração histórica, remoções indevidas, reutilização de identidade e alterações sem versionamento.

A cadeia lógica é:

`bytes -> provenance -> snapshot integrity -> temporal immutability`

## Princípios da reforma

- IDs públicos `P0.S3.M01` a `P0.S3.M04` preservados.
- `run_module(inputs, config)` preservado em todos os módulos.
- Formatos legados de manifests continuam aceitos por normalização interna.
- Paths absolutos de runtime não participam de digests canônicos.
- Hashing de arquivos é feito em streaming.
- O número de módulos é derivado do registry, não hardcoded.
- Lineage material é validado quando `producer_module_id`/`parents` existem, sem exigir que fases ainda não implementadas forneçam essa telemetria.
- Mutabilidade é explícita quando `mutability_class` está presente e possui fallback compatível para artefatos legados.
- Primeiro release é tratado explicitamente como `genesis`.
- Histórico pode usar cadeia append-only opcional com `record_hash` e `previous_record_hash`.
- Findings críticos tornam o artefato/fase **NOT READY para promoção**, mas não interrompem automaticamente o desenvolvimento.

## Classes de mutabilidade

- `IMMUTABLE`: não pode mudar nem desaparecer silenciosamente.
- `APPEND_ONLY`: pode apenas crescer por novos registros/versões; truncamento é crítico.
- `VERSIONED`: pode mudar apenas com version bump estritamente maior.
- `REPLACEABLE`: pode ser regenerado no mesmo identity/path conforme política do produtor.
- `EPHEMERAL`: artefato temporário, não deve ser tratado como histórico permanente.

## Outputs da subfase

Todos os outputs da S3 são expostos como outputs técnicos da fase para consumo posterior pelo Evidence Builder, Control Tower e Release Readiness sem alterar as conexões diretas de outras subfases neste pacote isolado:

- `hash_integrity_report`
- `lineage_integrity_report`
- `artifact_manifest_audit_report`
- `artifact_integrity_report`
- `immutability_report`

## Não faz

Não processa dado econômico, não cria feature, não prevê, não gera candidatos, não ranqueia, não monta carteira, não executa trades e não corrige automaticamente outros módulos.
