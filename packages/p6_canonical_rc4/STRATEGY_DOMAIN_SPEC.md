# Canonical Strategy Domain

O domínio canônico contém `InstrumentReference`, `OptionContractReference`, `ExecutableQuote`, `StrategyLeg`, `StrategyCandidate`, `TargetPayoffRecord`, `ScenarioEvaluation`, `CandidateRiskSummary`, `GreekState`, `CandidateGenerationTrace`, `SolverResult` e os records de publicação.

## Identidade

`candidate_id` depende do conteúdo econômico: underlying, decision time, pernas canônicas, quantidades, objective family e policy version. Ordem acidental de geração não participa do ID.

## Multi-leg invariants

- nenhuma perna sem instrumento observado;
- quantidade estritamente positiva no record de perna e lado separado;
- moeda, bolsa, multiplier, exercise style e settlement preservados;
- legs opostas idênticas são simplificadas na canonicalização;
- nenhuma combinação publicada sem prova de perda máxima finita.
