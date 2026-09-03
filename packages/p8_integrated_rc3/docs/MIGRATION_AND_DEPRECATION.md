# Migração e Deprecação

## Para consumidores novos

Use:

- APIs de subfase (`s01_boundary`, `scenario_engineering`, `risk_state`, `s05_optimization`, `s06_risk_lifecycle`, `subphases.s07...s10`);
- `phase_08_portfolio_control.integration` para traduções entre blocos;
- contracts canônicos e schemas gerados.

## Compatibilidade RC0

Continuam disponíveis:

- `agent1_integration`
- `agent2_bundle`
- `agent3_integration`
- `agent5_integration`

Esses nomes refletem o processo de construção, não o domínio. Não devem receber novas responsabilidades.

## Plano RC1

1. criar aliases de domínio para cada facade;
2. emitir warnings de deprecação em CLIs históricas;
3. migrar testes para APIs canônicas;
4. remover imports públicos de nomes de agentes somente após consumer migration;
5. preservar adapters explícitos, sem incorporar traduções aos módulos econômicos.
