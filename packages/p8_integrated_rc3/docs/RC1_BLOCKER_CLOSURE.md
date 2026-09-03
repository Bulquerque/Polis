# RC1 — Fechamento dos bloqueadores da RC0

## Bloqueadores fechados

1. **Semântica de PnL multi-horizonte**
   - O cubo declara `CUMULATIVE_FROM_DECISION` ou `INCREMENTAL_STEP`.
   - A fronteira S4→S5 converte cumulativo em incrementos antes do objetivo, CVaR e stresses.

2. **Ausência econômica não vira zero**
   - Entry cash flow, capital, margem, maximum loss e liquidez têm qualidade/status explícitos.
   - Candidato ativo com economics ausente é bloqueado.
   - Maximum loss só recebe `PROVEN` quando existe prova qualificada.

3. **Carteira completa separada do delta**
   - Hedge, lifecycle e emergência consomem a carteira completa no primeiro horizonte.
   - Execução consome apenas deltas autorizados.
   - Posições inalteradas continuam visíveis a expiry, assignment e margin-call.

4. **Segurança runtime aplicada end-to-end**
   - `HOLD_NO_NEW_RISK`, `CANCEL_OPEN_ORDERS`, `CLOSE_ONLY`, `RISK_REDUCTION_ONLY`, `HEDGE_ONLY`, `CONTROLLED_FLATTEN` e `HALT` são aplicados na execução.
   - Comandos são sequenciados, idempotentes, temporais e vinculados ao hash do estado.

5. **Hard constraints fail-closed**
   - Greek obrigatório ausente bloqueia a decisão.
   - Bounds obrigatórios short entram no pre-check de capital.
   - Constraint não pode desaparecer por falta de capability.

## Problemas adicionais fechados

- Ordens abertas atravessam S6→S7/S8 com sinal e atribuição virtual.
- Virtual-only realloc não fabrica `BUY_TO_OPEN`.
- Fill sem preço não vira preço zero.
- Hashing/serialização unificados em uma única autoridade.
- Accounting/auditoria multi-moeda usam FX funcional explícito.
- PnL indisponível permanece indisponível na evidência S10.
- Auditoria detecta adulteração de agregados funcionais.
- S6 recebeu regressões para lifecycle, hedge, emergência e finalização.
- Custo de transação não pode ser omitido de override de otimização.
- Opções exigem dividend yield, dividend economics, custo de exercício e borrow explicitamente declarados.
- Testes de CLI em subprocessos não dependem mais de um `PYTHONPATH` residual.
- `.git`, `.coverage`, caches e bytecode foram excluídos do manifesto e do ZIP.

## Evidência final

- 624 testes aprovados com warnings tratados como erro;
- 119 schemas válidos;
- 446 arquivos Python compilados;
- auditoria estática sem broad exceptions, placeholders ou schemas abertos;
- wheel com 310 arquivos e nenhum artefato proibido;
- instalação limpa e smoke test aprovados;
- 93,18% de statements e 75,66% de branches cobertos.

## Limites que permanecem externos

- Consumer real da P9 vNext.
- Autorização e consumer real da P0.
- Qualificação econômica prospectiva.
- Broker/market adapters live.

Esses itens mantêm `production_promotion_allowed=false`, mas não reabrem os bloqueadores internos da RC0.
