# P1.S1 + P1.S2 — Compatibility-First Modernization (Hardened)

## Surface congelada
- 5 subfases da P1 preservadas.
- 18 module IDs preservados.
- `run_phase(inputs, config)` preservado.
- 7 inputs públicos da fase preservados.
- 7 outputs públicos P1 -> P2 preservados.

## Modos de contrato
### `LEGACY_V1` — default
Modo seguro para integração com S3–S5 originais. Mantém o grain legado e bloqueia antecipadamente configurações multi-capture incompatíveis.

### `CAPTURE_V2` — opt-in
Permite múltiplos datasets/partições/páginas por `source_id` em S1/S2. Deve ser usado apenas depois da modernização coordenada de S3–S5/P2.

## Melhorias principais
### P1.S1
1. Registry dataset-centric com adapter metadata e credential handles.
2. Validação recursiva de secrets e forbidden economic fields.
3. Adapter explícito desconhecido pode falhar cedo em modo strict.
4. `RunContext` com `run_id`, `as_of_time`, mode, policies, storage e `contract_mode`.
5. Timestamps normalizados em UTC e timezone IANA validada.
6. Planner determinístico com dataset/partition/task identities.
7. `LEGACY_V1` protege downstream antigo contra multi-capture incompatível.

### P1.S2
1. `SourceAdapter`, `AdapterRegistry`, `CredentialResolver`, `HttpClient` e `RawCaptureEnvelope`.
2. Runtime credentials não são persistidas nos artifacts.
3. Paginação genérica: offset/total, page/total-pages, next-token.
4. BLS: batches de até 50 séries e janelas de até 20 anos.
5. SHA-256 calculado sobre bytes exatos.
6. `CAPTURE_V2` suporta múltiplos captures por source em S1/S2.
7. SEC exige User-Agent identificável.
8. Falhas de provider são registradas em `attempts` em vez de destruir silenciosamente evidência.

## Bridge de compatibilidade
O runner propaga o `run_id` validado para `config["ingestion_run_id"]`, porque S3–S5 legacy ainda consultam esse campo. Isso corrige o `run-fixture` sem mudar contratos públicos nem editar S3–S5.

## Limites conhecidos
- Multi-capture end-to-end continua bloqueado por default até S3–S5/P2 serem atualizados.
- O error lifecycle completo será fechado em S5.
- Streaming/bulk e discovery provider-specific ainda podem ser aprofundados.
