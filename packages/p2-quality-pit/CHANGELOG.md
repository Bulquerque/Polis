# Changelog

## RC4.1

- módulos documentados sem marcador_vazio_antigo;
- inputs obrigatórios separados de feedback opcional;
- outputs e forbidden fields declarados;
- subfases documentadas;
- testes contratuais reais adicionados.

## P2.S1 hardening — 2026-07-23

- preservados os 3 IDs de módulos, 7 inputs públicos e 3 outputs da subfase;
- `P2.S1.M01` passou a reconciliar handoff, snapshots, inventory, readability e referências disponíveis sem fabricar hashes;
- `P2.S1.M02` passou a materializar CSV/JSON/JSONL e Parquet quando há engine disponível, recalcular SHA-256, validar tamanho e preservar provenance por linha;
- modo legado permanece explicitamente marcado como `descriptor_compat` e nunca afirma `physical_hash_verified=true`;
- `P2.S1.M03` passou a gerar qualidade determinística, versionada e explicável (`quality_status` / `quality_reasons`), preservando os campos legados;
- adicionados testes operacionais com arquivos físicos, drift de hash, strict mode e degradação de qualidade;
- corrigido `INTERNAL_CONTRACTS.yaml` de 14 para 17 módulos, alinhado ao `MODULE_IO_MATRIX.yaml`.

## 2026-07-23 — Integrated P2 Clean Drop-In

- Unified S1/S2, S3/S4 and S5/S6 implementation patches on the original RC4.1 P2 surface.
- Preserved 7 public inputs, 20 public outputs, 17 module IDs, module graph, public schemas and downstream contracts.
- Reconciled S2↔S4 option identity while retaining `contract_key` as an opaque compatibility surface.
- Replaced the private synthetic semantic executor with explicit-wrapper dispatch; no production field fabrication remains in that path.
- Removed remaining hard-coded production fixture-date fallbacks.
- Fixed daily `as_of_date` fallback to preserve intraday causal availability instead of treating a date-only cutoff as midnight.
- Added strict physical full-P2 mini-run regression coverage.
- Added `qualification/P2_INTEGRATION_COMPATIBILITY_REPORT.md` and module-by-module comparison CSV.

## 2026-07-23 — Final hardening after module-by-module audit

- centralized S2/S4 canonical option economic identity in `_option_identity.py`;
- centralized downstream temporal parsing on S2 temporal primitives and fixed date-only cutoff handling in S4/S6;
- added explicit corporate-action semantics: PIT factor resolved, OHLC not silently rewritten;
- separated market tradability from execution-data readiness without changing legacy `tradability_flag`;
- added additive strict production profile in `profiles.py`;
- added optional strict schema blocking and strict rejection of `LEGACY_UNVERIFIED` handoffs;
- clarified qualification documentation without granting global production authorization;
- added `INTEGRATION_AND_CORRECTION_GUIDE.md` with project-level corrections and integration gates.
