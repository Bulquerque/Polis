# Compatibility matrix

| Produtor | Contrato | Status | Observação |
|---|---|---|---|
| P8.S1–S2 | candidate states, decision snapshot and dual-book lineage | NATIVE_BY_REFERENCE | S10 preserva IDs e references; não importa internals. |
| P8.S3–S4 | scenarios, risk, margin, liquidity and sizability evidence | NATIVE_BY_REFERENCE | S10 audita os hashes e publica os refs para P9. |
| P8.S5–S6 | objective, constraints, target, risk gate and authorization | NATIVE_BY_REFERENCE | S10 não recalcula o optimizer; audita a cadeia de autorização. |
| P8.S7–S8 | `P8_STATEFUL_EVIDENCE_BUNDLE_V1` | NATIVE | Contrato principal do auditor independente. |
| P8.S9 | `RuntimeEvidenceBundle` | NATIVE_BY_ARTIFACT_REF | S10 referencia o bundle content-addressed; não duplica modelos S9. |
| P9 vNext | `P8_TO_P9_EVALUATION_HANDOFF_V1` | NATIVE | Evidence classes, commitment, maturity hints e lineage. |
| P9 RC4.1 | flat reports and generic executor | UNSUPPORTED_WITHOUT_EXPLICIT_ADAPTER | Nenhum downgrade silencioso; adapter seria loss-aware e research-only. |
| P0 | `P8_RELEASE_QUALIFICATION_HANDOFF_V1` | NATIVE | Release evidence e production lock. |

## Regra

Compatibilidade significa semântica, clocks, hashes, grain e authority compatíveis. Similaridade de nomes ou presença de campos não é compatibilidade.
