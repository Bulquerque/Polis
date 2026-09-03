# P0.S5 — Code Quality, Anti-Bloat & Static Analysis

## Missão

A P0.S5 é o auditor estático de engenharia da Fase 0. Ela examina o source tree e os inventários técnicos para identificar degradação estrutural do código antes que essa degradação se transforme em acoplamento oculto, baixa manutenibilidade ou risco de release.

A subfase não modifica código, não chama agentes e não corrige automaticamente findings. Ela observa, classifica, atribui ownership e produz evidência para Evidence, Control Tower, Release Gate e Feedback.

## Módulos

### P0.S5.M01 — duplicate_file_detector
Detecta duplicatas exatas por SHA-256 e as classifica para evitar tratar como equivalentes:
- duplicação acidental;
- utilidade comum duplicada;
- mirror de schema/source-of-truth;
- fixture de teste;
- package marker (`__init__.py`);
- duplicata explicitamente allowlisted.

Duplicações legítimas permanecem auditáveis, mas não precisam bloquear release. Duplicação de infraestrutura comum permanece bloqueante.

### P0.S5.M02 — monolith_code_detector
Aplica a policy canônica de Clean Code:
- `max_python_file_lines`;
- `max_function_lines`;
- `max_class_lines`;
- `max_module_public_functions`;
- `max_cyclomatic_complexity`.

A chave legada `max_file_lines` é aceita apenas por compatibilidade. Exceções precisam ser materializadas com path e justificativa explícita.

### P0.S5.M03 — forbidden_import_detector
Analisa imports via AST e detecta:
- imports proibidos declarados em policy;
- imports dinâmicos literais (`__import__`, `importlib.import_module`);
- imports internos entre fases quando o source path permite resolver ownership;
- violações de fronteira arquitetural.

Imports de `quant_pipeline.common` permanecem permitidos como infraestrutura transversal.

### P0.S5.M04 — hidden_global_state_detector
Detecta:
- globals mutáveis em import time;
- mutação de estado no nível do módulo;
- uso de `global` para mutação;
- objetos stateful inicializados em import time;
- secrets hardcoded;
- paths absolutos dependentes do ambiente.

Nomes de variáveis de ambiente, constantes imutáveis e allowlists explícitas não devem gerar falso positivo.

### P0.S5.M05 — module_contract_coverage_checker
Verifica cobertura estrutural entre registry, contratos YAML e testes esperados. Quando um `source_tree_manifest` materializado é fornecido adicionalmente, também verifica implementação Python correspondente aos IDs canônicos.

### P0.S5.M06 — code_style_quality_reporter
Agrega os cinco relatórios anteriores preservando ownership. Um problema localizado em P4 não marca automaticamente P0-P9 como falha.

Findings sem ownership resolvível são atribuídos à P0.S5 como problema do control plane, enquanto findings com `module_id` ou path de fase são atribuídos à fase correspondente.

## Regras de design

- IDs, nomes dos seis módulos e `run_module(inputs, config=None)` permanecem estáveis.
- A lógica interna é dividida em componentes privados `_s5_*` específicos, evitando `utils.py`, `helpers.py` ou `misc.py` genéricos.
- Nenhum componente da S5 importa função privada da S1.
- A S5 não altera fluxo econômico, features, forecasts, candidatos, ranking, portfólio, backtest ou P&L.
- Outputs continuam compatíveis com os consumidores P0.S4, P0.S6, P0.S8 e P0.S9.

## Política de falha

Falhas estruturais de input/materialização geram fail-fast.

Violações encontradas no código são materializadas em relatórios com `PASS/FAIL` e `release_blocking`, permitindo que a P0 alerte e classifique readiness sem interromper automaticamente o desenvolvimento da fase afetada.
