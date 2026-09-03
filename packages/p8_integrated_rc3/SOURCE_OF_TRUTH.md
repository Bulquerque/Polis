# Source of Truth — P8 Integrated RC2

## Autoridade

A autoridade é:

1. `src/`;
2. contratos Pydantic estritos;
3. schemas gerados;
4. registries;
5. manifesto final;
6. receipts content-addressed.

## Regras invariáveis

1. Uma árvore e uma wheel.
2. P7 fornece preferência ordinal, nunca retorno esperado ou peso.
3. P6 define shape; P8 define scale.
4. Ausência nunca vira zero.
5. Event log é autoridade; checkpoint é cache.
6. Challenger não executa.
7. Runtime adaptation apenas reduz risco.
8. S10 audita por implementação independente.
9. Bridges externos vivem somente em `compatibility/`.
10. Nenhum bridge altera os contratos nativos de S1/S2.
11. Hash da origem e hash P8 possuem semânticas separadas e registradas.
12. Opções sem lifecycle modelado não avançam para execução.

## Compatibilidade RC3

A única autoridade para P5/P6/P7 RC3 é:

```text
quant_pipeline.phase_08_portfolio_control.compatibility.p567_rc3
```

Ela publica:

- `P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1`;
- `P6_CANDIDATE_ECONOMIC_PACKAGE_V1`;
- `P7_TO_P8_RANKING_HANDOFF_V1`;
- `P567_RC3_TO_P8_ADAPTATION_RECEIPT_V1`.

Não é permitido adicionar parsing RC3 dentro dos módulos S1–S10.

## Versão

- package: `quant-pipeline-phase08-integrated`
- release: `0.3.0rc3`
- Python: `>=3.13,<3.15`
- production promotion: `false`
