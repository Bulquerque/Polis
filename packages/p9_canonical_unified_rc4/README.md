# P9 — Evaluation, Robustness, Prospective Validation and Learning — Hardened 5

Package version: **0.1.0rc4.post2**  
Modules: **70**  
Subphases: **10**

## Hardened 5 closure

This revision closes the seven internal blockers found in the Hardened 4 audit:

- executed outcomes are point-in-time gated by close, settlement and availability;
- exploration/confirmation/robustness budgets obey committed fractions and wall-clock policy;
- backtest trials enforce memory, worker labels and aggregate CPU budgets;
- all prospective S7 materialized records are content-addressed and bound to their upstream sources;
- Sharpe/overfitting evidence is bound to the target configuration and trial family;
- attribution and promotion gate receipts are bound to the exact S8 artifact, run, cycle and challenger set;
- cycle release requires same-run receipts, non-empty successful tests, minimum coverage and authenticated source/wheel references;
- S7 canonicalization is deterministic across Python hash seeds;
- validation tools ignore or clean bytecode produced by compilation/testing.

Current reproduced validation: **587 passed, 7 externally skipped, 0 failed**; **92.21% statements**, **74.03% branches**, **88.58% combined**. The skipped tests require a separate frozen P0–P7 reference tree and are not silently treated as passes.

`production_promotion_allowed = false` and `economic_qualification = false` remain mandatory until prospective real-market evidence is supplied.

---

# P9 Canônica Unificada RC3

Implementação consolidada da Fase 9 com compatibilidade explícita e fail-closed com os snapshots qualificados de P0–P8.

A RC3 mantém os 70 módulos científicos da P9 isolados das implementações históricas. Diferenças de namespace, schemas, envelopes, canonicalização e governança ficam concentradas em `quant_pipeline.phase_09.compatibility`, com adapters tipados e testes contra os consumidores reais.

## Estrutura científica

| Subfase | Responsabilidade | Módulos |
|---|---|---:|
| P9.S1 | Evidência, lineage, replay e maturidade | 6 |
| P9.S2 | Governança experimental e hiperparâmetros | 6 |
| P9.S3 | Backtest tournament temporal | 7 |
| P9.S4 | Performance, risco, fatores e capacidade | 8 |
| P9.S5 | Bootstrap, inferência e overfitting | 8 |
| P9.S6 | Stress estrutural, cauda e resiliência | 8 |
| P9.S7 | Validação prospectiva e monitoramento | 8 |
| P9.S8 | Attribution e contrafactuais | 8 |
| P9.S9 | Competição, promoção e feedback | 7 |
| P9.S10 | Memória de pesquisa e release | 4 |
| **Total** |  | **70** |

## Compatibilidade P0–P8

| Fase | Fronteira | Estado qualificado |
|---|---|---|
| P0 | reports técnicos e dashboard | compatível com normalizadores e schema reais |
| P1 | manifest e lineage | compatível por fingerprint congelado |
| P2 | manifest, point-in-time e lineage | compatível por fingerprint congelado |
| P3 | evidência S31, belief feedback e memória contextual | compatível em processo isolado |
| P4 | manifest e lineage de features | compatível por fingerprint congelado |
| P5 | `signal_feedback_report` | aceito pelo consumer RC4.1 real |
| P6 | feedback de síntese | governado por P0; o snapshot RC4.1 não possui consumer direto |
| P7 | `ranking_feedback_report` | aceito pelo consumer RC4.1 real |
| P8 | evidência nativa e feedback promovido | perfil nativo limitado; FULL com suplementos explícitos |

### P8 → P9

O snapshot P8 `0.3.0rc3` é consumido pelos próprios modelos públicos da P8. O publisher materializa 20 papéis de evidência reais e gera o handoff canônico da P9.

- `P8_NATIVE_0_3_LIMITED`: aceito sem fabricar NAV temporal, drawdown, exposição, trace do otimizador ou marking policy.
- `FULL_V1`: aceito somente quando os seis artefatos faltantes são fornecidos com schema, produtor, clocks, hash e cardinalidade explícitos.

### P9/P0 → P8

A P9 produz a recomendação; a P0 continua sendo a única autoridade de ativação. O materializador gera o modelo exato `P9_TO_P8_PROMOTED_FEEDBACK_V1`, usa a canonicalização da P8 e foi executado contra `P8.S1.M04`, incluindo bounds, janela temporal e idempotência.

### P3

A P3 qualificada possui um `quant_pipeline` regular, incompatível com composição PEP 420 no mesmo processo. A integração usa subprocesso isolado com os modelos e consumers reais da P3, sem copiar contratos e sem contaminar o namespace da P9.

## Qualificação RC3

```text
591 testes P9 aprovados
631 testes P8 aprovados com a P9 presente
0 falhas
70/70 módulos registrados
10/10 subfases
238 módulos P9 importáveis
339 tokens registrados
11 contratos globais
13 schemas de compatibilidade
9/9 fingerprints P0–P8 verificados
```

Comandos principais:

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python tools/run_qualification.py --suite external_compatibility
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python tools/run_qualification.py --suite core
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python tools/aggregate_qualification.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python tools/import_sweep.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python tools/validate_p9_registries.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python tools/validate_release.py
python -m pip wheel . --no-deps -w dist
```

## Autoridade e limites

- P9 avalia e recomenda; P0 autoriza.
- Feedback só pode valer em ciclo posterior.
- Evidência ausente nunca vira zero, confiança, custo ou retorno.
- P6 permanece governada porque o pacote RC4.1 não oferece consumer direto.
- O perfil nativo atual da P8 é funcionalmente compatível em modo limitado; FULL exige evidência que a P8 não publica no handoff padrão.
- Qualificação econômica prospectiva e capital real não são autorizados por esta release.
