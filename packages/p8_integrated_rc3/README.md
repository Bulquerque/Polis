# P8 Integrated RC2

Release integrada da Fase 8: cenários, risco conjunto, otimização, lifecycle, execução, accounting, segurança em runtime e auditoria independente.

## Resultado

- 10 subfases e 58 módulos;
- uma árvore, uma wheel e uma versão;
- contratos estritos entre S1–S10;
- correções semânticas da RC1 preservadas;
- bridge tipado e content-addressed para `P5_P6_P7_COMPATIBILITY_HARDENED_RC3`;
- P5 RC3 materializado como bundles nativos e `BeliefRecord` S3;
- P6 RC3 materializado como pacotes econômicos unitários;
- P7 RC3 materializado como handoff ordinal conservado;
- produção desabilitada.

## Instalação

```bash
python -m pip install dist/quant_pipeline_phase08_integrated-0.3.0rc3-py3-none-any.whl
```

Python: `>=3.13,<3.15`.

## Compatibilidade P5–P7 RC3

```python
from quant_pipeline.phase_08_portfolio_control import adapt_p567_rc3_to_p8
```

O adapter aceita a publicação completa P5/P6/P7 RC3 e produz somente contratos nativos P8. Ele não converte score em retorno, não inventa capacidade de liquidez e bloqueia lifecycle não modelado.

Consulte `docs/compatibility/P5_P6_P7_RC3.md`.

## Testes

```bash
python -m pytest -q
```

A suíte inclui snapshots capturados da cadeia viva RC3, caminho all-abstained até S2, projeção ranked, falhas de conservação, ausência de economics e lifecycle de opções.

## Estado

```text
physical_integration = PASS
rc1_semantic_blockers = CLOSED
p5_p6_p7_rc3_package_coexistence = PASS
p5_p6_p7_rc3_no_action_path = PASS
p5_p6_p7_rc3_ranked_contract_path = PASS_FAIL_CLOSED
production_promotion_allowed = false
```
