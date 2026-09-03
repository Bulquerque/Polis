# Implementation notes

## M01 — Independent auditor

Recalcula candidate, order, fill, position, dual-book, cash, margin, collateral, liabilities, valuation, NAV, PnL e replay identities. O código não depende da implementação produtora.

## M02 — Qualification gate

Separa:

- technical validity;
- implementation robustness;
- statistical qualification/readiness;
- economic qualification, sempre `DEFERRED_TO_P9`.

DSR e PBO são diagnósticos locais. Não são usados para emitir ordens ou autorizar produção.

## M03 — P9 handoff

Exige evidence e lineage para todos os candidatos, inclusive bloqueados e não executados. Impede commitment posterior à decisão e impede factual/model-based ambiguity.

## M04 — Release publisher

Aceita somente paths relativos dentro do root, calcula hashes sobre bytes finais e bloqueia release se clean install, extraction, replay, P9 consumer ou namespace coexistence não estiverem aprovados.
