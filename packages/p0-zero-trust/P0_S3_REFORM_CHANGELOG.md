# P0.S3 Deep Reform — Change Log

## Preservado

- IDs `P0.S3.M01–M04`.
- Nomes públicos dos módulos e outputs.
- Assinatura `run_module(inputs, config=None)`.
- Compatibilidade com manifests CSV/YAML e registros legados.

## Implementado

### M01 — Hash Policy Enforcer
- hashing SHA-256 em streaming;
- resolução robusta do workspace sem `parents[6]` fixo;
- referências canônicas repository-relative em relatórios/digests;
- política criptográfica centralizada;
- parser de manifests compartilhado e testável.

### M02 — Lineage Integrity Checker
- remoção do `EXPECTED_MODULE_COUNT = 166` hardcoded;
- total esperado derivado do module registry;
- preservação do lineage estrutural contratos/módulos;
- lineage material opcional por `artifact_id`, `producer_module_id` e `parents`;
- detecção de producer desconhecido, parent inexistente e ciclos de runtime;
- compatibilidade com lineage digests legados e canônicos.

### M03 — Artifact Manifest Auditor
- separação semântica entre auditoria detalhada e resumo de integridade;
- distinção entre manifesto legível, target materializado e coverage;
- verificação forte de artefatos críticos declarados/materializados/hash-valid;
- `artifact_integrity_report` com component status de manifest/hash/lineage.

### M04 — Artifact Immutability Checker
- classes `IMMUTABLE`, `APPEND_ONLY`, `VERSIONED`, `REPLACEABLE`, `EPHEMERAL`;
- suporte explícito a baseline `genesis`;
- detecção de artifact immutable removido e append-only truncado;
- detecção de mutability policy violation;
- aviso não bloqueante para identidade legada baseada em path;
- cadeia histórica append-only opcional (`record_hash` + `previous_record_hash`);
- version comparison centralizada e mais robusta.

## Clean Code

- módulos públicos mantidos como adapters/orchestrators;
- utilidades internas separadas em `_p0_s3_shared.py`, `_p0_s3_artifacts.py` e `_p0_s3_lineage.py`;
- todos os arquivos S3 ficam abaixo do limite canônico de 350 linhas;
- todas as funções S3 ficam abaixo do limite canônico de 60 linhas;
- removidas dependências de helpers privados da S1.

## Escopo deliberadamente não alterado

Como este pacote contém **somente a subfase P0.S3 reformada**, contratos de consumo de P0.S4/P0.S6/P0.S8 não foram modificados. Os cinco reports da S3 foram expostos como `phase_outputs`, permitindo integração posterior sem quebrar bidirecionalidade de contratos externos.
