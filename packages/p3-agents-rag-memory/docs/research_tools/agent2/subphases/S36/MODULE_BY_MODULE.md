# Module by Module

## M01 — Market View Binding Builder

Liga operações às views P2, verifica campos e produz prontidão por operação. Não lê arquivos nem executa consultas.

## M02 — Snapshot, History and Liquidity Bundle

Qualifica handlers de snapshot, histórico e liquidez. Preço é RAW por padrão; política ajustada sem evidência upstream é bloqueada.

## M03 — Corporate Action and Cross-Asset Bundle

Qualifica ações corporativas e comparação descritiva. Ações são visíveis por anúncio/disponibilidade, não apenas por ex-date. Comparação não produz ranking.

## M04 — Option Contract and Chain Bundle

Qualifica contratos, cadeia e histórico de quotes. Contratos são visíveis por `first_seen_date`; cada cadeia usa a última quote visível por contrato.

## M05 — Surface Diagnostic Bundle

Qualifica diagnóstico de superfície. Exige IV observada e cobertura mínima; não resolve IV, não interpola e não calibra modelo.

## M06 — Consolidation and Qualification

Consolida cinco operações de mercado e quatro de opções, verifica snapshot comum, handler único e prontidão por modo para consumo da S40.
