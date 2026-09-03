# Migration V1 to V2

1. Consumidores devem preferir `phase7_strategy_handoff_manifest` e os painéis V2.
2. IDs atômicos antigos não são modelo canônico; a unidade passa a ser `StrategyCandidate` com `StrategyLeg`.
3. O adapter V1 permanece somente para transição.
4. P5 V2 será conectado por adapter após seu contrato ser congelado.
5. Remoção da projeção V1 exige consumer receipt da P7 e mudança major de contrato.
