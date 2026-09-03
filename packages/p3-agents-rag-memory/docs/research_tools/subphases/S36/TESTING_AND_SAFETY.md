# Testing and Execution Safety

## Estratégia anti-travamento

- testes em grupos sequenciais;
- timeout individual;
- `maxfail=1` durante diagnóstico;
- sem `pytest-xdist`;
- sem multiprocessing, fork ou threads auxiliares;
- compilação antes dos testes;
- suíte completa apenas após os grupos locais passarem.

## Grupos

- view binding;
- handlers de mercado;
- handlers de opções;
- qualificação;
- contratos e arquitetura;
- propriedades point-in-time;
- integração dos seis módulos.

## Falha fechada

Dados ausentes, timestamp ausente, IV ausente, snapshot incompatível e ajustes não comprovados não são preenchidos. A operação retorna bloqueio/degradação explícita ou falha de contrato.
