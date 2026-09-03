# Testes e segurança operacional

## Execução

- testes sequenciais;
- timeout por grupo;
- sem `xdist`;
- sem multiprocessing;
- sem `fork`;
- sem rede;
- falha imediata ao primeiro grupo quebrado.

## Grupos

- unitários;
- contratos e arquitetura;
- propriedades temporais;
- integração dos quatro módulos;
- compatibilidade P1/P2/S21;
- merge simulado;
- build e import do wheel;
- validação por extração limpa.

## Comando

```bash
python tools/run_tests_safe.py
```
