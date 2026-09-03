# Debugging da Release Integrada

## Ordem de diagnóstico

1. Validar manifesto e hash do artefato de entrada.
2. Conferir clocks: decision, cutoff, computed, available.
3. Conferir candidate conservation.
4. Conferir bindings explícitos S2→S4.
5. Conferir NPZs e candidate IDs S4→S5.
6. Conferir dual book S6→S7.
7. Conferir order/fill conservation.
8. Conferir ledgers, NAV e PnL.
9. Conferir source state hash do comando runtime.
10. Executar auditoria independente S10.

## Comandos

```bash
python tools/run_qualification.py
python tools/export_schemas.py
python tools/verify_manifest.py
```

## Falhas comuns

- `ContractMappingError`: faltou binding econômico; não adicione default.
- `CrossBoundaryIntegrityError`: IDs, dual book ou hashes não fecharam.
- policy hash mismatch: política foi alterada sem recalcular seu content hash.
- input unavailable at decision time: `available_at` não respeita a semântica do consumer.
- scenario reduction unsafe: use o conjunto completo ou aumente o conjunto reduzido.
