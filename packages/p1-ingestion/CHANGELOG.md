# Changelog

## RC4.1

- módulos documentados sem marcador_vazio_antigo;
- inputs obrigatórios separados de feedback opcional;
- outputs e forbidden fields declarados;
- subfases documentadas;
- testes contratuais reais adicionados.

## P1.S1/S2 compatibility hardening
- Added default `LEGACY_V1` contract mode and opt-in `CAPTURE_V2`.
- Added early compatibility guard for multi-capture against legacy S3-S5.
- Preserved validated `run_id` through legacy downstream via runner bridge.
- Normalized temporal comparisons to UTC and validated IANA timezones.
- Hardened adapter/credential validation and SEC User-Agent requirement.
- Expanded phase-specific tests from 56 original to 66 passing tests.
- Added comparative compatibility/superiority evidence report.
## Integrated compatibility-first replacement (2026-07-23)
- Merged hardened S1/S2 capture architecture with S3/S4/S5 persistence, integrity, snapshot and handoff reforms.
- Preserved five subphases, eighteen module IDs, seven public phase inputs/outputs, and `run_phase(inputs, config)`.
- Added LEGACY_V1 and CAPTURE_V2 compatibility modes, provider adapter/credential/HTTP foundation, exact-byte hashing, atomic storage, multi-capture snapshots, error provenance, and fail-closed P2 multi-snapshot bridge.
- Added regression and adversarial tests for ID normalization, timestamp safety, secret redaction, streaming local files, provider error provenance, and P2 snapshot matching.

