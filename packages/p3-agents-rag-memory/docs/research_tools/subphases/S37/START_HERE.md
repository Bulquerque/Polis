# Comece aqui

## Ordem de leitura

1. `SOURCE_OF_TRUTH.md`
2. `subphases/P3_S37_macro_observation_tool_suite.md`
3. `docs/MODULE_BY_MODULE.md`
4. `docs/POINT_IN_TIME_AND_BACKTEST.md`
5. `INTEGRATION_GUIDE.md`
6. `docs/TESTING_AND_SAFETY.md`

## Validação segura

```bash
python tools/validate_package.py
python tools/run_tests_safe.py
```

O runner executa grupos sequencialmente, com timeout individual e sem paralelismo.

## Integração

Esta entrega é um overlay aditivo. Não substitua arquivos de `P3.S1–P3.S31`.
Use `tools/merge_overlay.py --source . --target <P3_ROOT>` em uma cópia limpa e valide o resultado antes de promover.
