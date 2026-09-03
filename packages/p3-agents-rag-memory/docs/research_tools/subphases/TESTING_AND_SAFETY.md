# Testes e segurança de execução

## Estratégia anti-travamento

A suíte é dividida em grupos pequenos e executada sequencialmente. `tools/run_tests_safely.py` usa timeout por grupo e encerra o subprocesso em caso de excesso.

Ordem:

1. compilação;
2. unitários de snapshot;
3. unitários de retrieval;
4. unitários de handlers e integridade;
5. contratos S21/schemas;
6. propriedades point-in-time;
7. integração da subfase.

Não é usado `pytest-xdist`, multiprocessing ou fork.

## Cobertura funcional

- seis operações públicas;
- hashes e snapshots;
- requests inválidos;
- filtros PIT;
- deduplicação;
- fallback de raw evidence;
- proveniência parcial e completa;
- modos forenses bloqueados;
- integração M01→M05;
- serialização S21.

## Comandos

```bash
python tools/validate_package.py --p3-base-src /p3/src
python tools/run_tests_safely.py --p3-base-src /p3/src --timeout 60
```
