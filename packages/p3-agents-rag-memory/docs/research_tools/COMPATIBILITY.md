# Compatibilidade

## Base

- Contrato base: `P3_RC4_1_81_MODULES`;
- wrappers antigos esperados: 81;
- wrappers após overlay: 96;
- novos wrappers: 15.

## Cross-phase

- S35 depende de S12/S20 e da fronteira S33;
- S36 consome views P2 de mercado, liquidez, corporate actions e opções;
- S37 consome views P2 macro e calendários;
- S35–S37 entregam bundles para S40;
- não há P3→P5 direto;
- não há autoridade de backtest, portfólio ou execução.
