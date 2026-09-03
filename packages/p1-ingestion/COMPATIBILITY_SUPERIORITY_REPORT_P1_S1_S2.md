# P1.S1 + P1.S2 — Compatibility Hardening and Comparative Evidence

## Veredito
Esta versão é uma modernização **compatibility-first** das subfases `P1.S1` e `P1.S2`.
Ela preserva a topologia pública original e melhora segurança, identidade, planejamento, captura e extensibilidade.

A compatibilidade é deliberadamente dividida em dois modos:

- `LEGACY_V1` (default): compatível com `S3–S5` originais. Impede cedo qualquer multi-capture que o downstream antigo não consiga representar.
- `CAPTURE_V2` (opt-in): habilita múltiplos datasets/partições/páginas por `source_id` em `S1/S2`; exige modernização posterior de `S3–S5/P2` para persistência end-to-end desse grain.

## Evidência comparativa objetiva

| Critério | Original | Nova versão endurecida |
|---|---|---|
| Testes phase-specific | 56 passed | 66 passed |
| IDs / I/O dos módulos S1/S2 | baseline | preservados |
| 7 outputs públicos finais P1 | baseline | preservados |
| Nested secret em source definition | aceito indevidamente | rejeitado recursivamente |
| SHA-256 de `raw_bytes` | podia divergir do SHA-256 real | SHA-256 exato dos bytes |
| `run_id` no snapshot/handoff legacy | degradava para `run-fixture` | preserva `run_id` real |
| Multi-capture com downstream legacy | falha tardia/confusa | bloqueio antecipado e explícito em `LEGACY_V1` |
| Multi-capture em S1/S2 | não suportado adequadamente | suportado em `CAPTURE_V2` |
| Credential resolution | não operacional | runtime resolver sem persistir segredo |
| Adapter/transport layer | ausente | SourceAdapter + registry + HttpClient |
| Paginação | ausente | offset/total, page/total-pages, next-token |
| BLS batching | ausente | lotes até 50 séries / janelas até 20 anos |
| SEC identification | não implementada | User-Agent obrigatório no adapter SEC |
| Time comparison | superficial | timestamps normalizados para UTC e timezone IANA validada |

## Compatibilidade comprovada

1. Os mesmos 7 nomes de outputs públicos são emitidos.
2. O caminho legacy `1 source -> 1 capture` executa a fase completa.
3. O output legacy da nova P1 é aceito por `P2.S1.M01 phase1_handoff_validator` sem patch manual.
4. `run_phase(inputs, config)` e os 18 module IDs permanecem intactos.
5. `INPUT_CONTRACTS.yaml`, `OUTPUT_CONTRACTS.yaml`, `MODULE_IO_MATRIX.yaml` e `INTERNAL_CONTRACTS.yaml` permanecem estruturalmente compatíveis.

## Melhorias de compatibilidade adicionadas nesta revisão

### 1. Contract mode explícito
`LEGACY_V1` é o default. Se uma configuração tentar gerar mais de uma task/captura por `source_id`, a fase falha em `P1.S1.M03` com mensagem explícita antes de chegar a S3.

`CAPTURE_V2` só deve ser usado quando o downstream estiver modernizado.

### 2. Bridge de `run_id`
O runner propaga o `run_id` validado por `P1.S1.M02` para a configuração legacy consumida por S3–S5, sem alterar a assinatura pública do runner.

### 3. Temporal hardening
Timestamps são normalizados para UTC; comparação `start_time/end_time` usa instantes reais, não ordem lexicográfica. Timezones são validadas via IANA/ZoneInfo.

### 4. Adapter safety
Adapter explícito desconhecido pode ser rejeitado em modo strict. Em modo compatível, fica marcado como não registrado em vez de ser silenciosamente tratado como válido.

### 5. SEC fair-access safety
O adapter SEC exige um User-Agent identificável, seja por header explícito ou por credential handle.

## Limites deliberados

Esta entrega não modifica S3–S5. Portanto:

- `CAPTURE_V2` não deve ser promovido a execução end-to-end antes da modernização de S3–S5/P2.
- Error lifecycle/partial success já nasce em `attempts`, mas S5 original ainda não o consome integralmente.
- Streaming de arquivos muito grandes e provider-specific discovery ainda são próximos passos.
- `health_check`, `discover` e `plan_tasks` existem como interface, mas ainda não estão integrados ao lifecycle completo de todos os providers.

## Critério de superioridade usado
A nova versão é considerada superior apenas em propriedades demonstradas por teste ou inspeção verificável: segurança de secrets, hash exato, preservação de run identity, validação temporal, capacidade modular, compatibilidade legacy e cobertura de testes.
