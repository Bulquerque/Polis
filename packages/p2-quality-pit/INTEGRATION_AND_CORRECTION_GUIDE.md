# Guia de Integração, Correções e Manutenção — P2 Clean Drop-In RC4.1

## 1. Objetivo deste pacote

Este pacote substitui a P2 original mantendo a mesma superfície pública e corrigindo a implementação interna.
A intenção é permitir a troca da pasta `phase_02_extracted/phase_02_quality_pit_agent_package_RC4_1` sem redesenhar P1, P3, P4 ou P6.

### Superfície congelada e preservada

- 6 subfases;
- 17 IDs de módulos;
- 7 inputs públicos;
- 20 outputs públicos;
- `MODULE_IO_MATRIX.yaml` preservado;
- contratos individuais dos 17 módulos preservados;
- schemas públicos preservados;
- conexões P1→P2 e P2→P3/P4/P6 preservadas;
- `contract_key` continua sendo uma chave pública opaca para joins/igualdade; consumidores não devem parsear sua representação textual.

## 2. O que foi corrigido dentro desta P2

### P2.S1 — Chain of custody e materialização

- M01 reconcilia handoff, registry, inventory, snapshots, readability, schema hints e ingestion errors.
- M02 lê arquivos físicos CSV/JSON/JSONL/Parquet, verifica tamanho e SHA-256 e preserva provenance por linha.
- O modo legado continua disponível apenas para compatibilidade e é marcado como não verificado fisicamente.
- M03 produz qualidade determinística e explicável (`quality_status`, `quality_reasons`).
- Não são mais fabricados hashes ou resultados positivos para fazer fixtures passarem.

### P2.S2 — Point-in-time e identidade

- timestamps são normalizados com timezone e semântica de cutoff explícita;
- `YYYY-MM-DD` usado como cutoff é tratado como fim do dia, evitando falso future-data intradiário;
- identidade de instrumento, observação e contrato de opção são separadas;
- S2 e S4 usam a mesma autoridade de identidade econômica de opções (`_option_identity.py`);
- `record_domain` cria roteamento canônico para MACRO/BENCHMARK/CALENDAR/CORPORATE_ACTION/UNDERLYING/OPTION/DOCUMENT/EVENT/CONTEXT;
- nenhuma opção sintética ou economia ausente é inventada.

### P2.S3 — Mercado estruturado

- macro BR/US não é mais preenchido artificialmente quando inexistente;
- benchmark é filtrado por domínio;
- calendário não assume `is_trading_day=True` quando desconhecido;
- corporate actions separam knowledge-time de effective-time;
- underlying faz joins reais com calendário, qualidade e corporate actions;
- o fator de ajuste PIT é resolvido sem reescrever silenciosamente OHLC;
- `corporate_actions_applied_pit` é mantido por compatibilidade, mas os campos novos deixam explícito que P2 resolveu o fator e não reescreveu os preços;
- trade panel não inventa bid/ask, custo zero ou liquidez positiva;
- `tradability_flag` foi preservado e agora é acompanhado por `market_tradable_flag`, `execution_data_ready` e `execution_readiness_status`.

### P2.S4 — Opções, custo e liquidez

- contrato não recebe strike/expiry/type fictícios;
- identidade econômica de opção é compartilhada com S2;
- quotes resolvem exatamente para contratos existentes e rejeitam missing/ambiguous matches;
- crossed markets, stale quotes, datas após expiry e feeds não primários são tratados explicitamente;
- custo/liquidez preservam métricas auditáveis e não convertem ausência de dados em execução perfeita.

### P2.S5 — Contexto/documentos/eventos

- documentos e eventos não são fabricados para evitar painéis vazios;
- qualidade da fonte é ligada ao `source_quality_panel`;
- eventos derivados de publicação de documento são explicitamente identificados como tal;
- forbidden fields são verificados recursivamente.

### P2.S6 — Quality gate e handoffs

- substituído o antigo “count > 0 = PASS” por gate real;
- valida schemas, PIT, duplicatas, sanidade de mercado, integridade referencial e relações cross-panel;
- status: PASS/WARN/DEGRADED/BLOCK;
- handoffs são específicos por target e continuam preservando os campos legados;
- modo estrito pode bloquear schema drift, dados físicos não verificados, source quality ausente, DEGRADED e LEGACY_UNVERIFIED.

## 3. Melhorias transversais de arquitetura e clean code

- `_module_executor.py` não fabrica mais semanticamente PASS/timestamps/registros; ele mantém apenas compatibilidade e dispatch explícito.
- uma única primitive compartilhada de identidade econômica de opções evita drift S2↔S4;
- S3/S4/S6 reutilizam a autoridade temporal de S2;
- defaults produtivos artificiais foram removidos;
- helpers foram mantidos pequenos e por responsabilidade, sem criar framework abstrato excessivo;
- P2 continua sem HTTP/API keys/retries/paginação de providers: isso pertence à P1.

## 4. Profile recomendado para execução rigorosa

Use:

```python
from quant_pipeline.phase_02_quality_pit.profiles import strict_production_config

config = strict_production_config({
    "allowed_roots": ["/caminho/para/raw/snapshots"],
    "as_of_date": "2026-07-23",
    "default_timezone": "UTC",
})
```

O profile ativa:

- `strict_physical_validation=True`
- `strict_temporal_validation=True`
- `strict_source_quality=True`
- `fail_on_blocked_critical_source=True`
- `strict_schema_validation=True`
- `allow_degraded_handoffs=False`
- `allow_legacy_unverified=False`

Não torne esse profile default global sem testar consumidores legados; ele é propositalmente mais estrito que o modo drop-in.

## 5. Como substituir a P2 antiga

1. Faça backup da pasta original.
2. Substitua exatamente:

   `phase_02_extracted/phase_02_quality_pit_agent_package_RC4_1/`

   pela pasta de mesmo nome deste ZIP.
3. Não renomeie a fase, módulos ou artifacts.
4. Não copie os ZIPs intermediários S1/S2, S3/S4 ou S5/S6 para o projeto final.
5. Recalcule manifests/hashes do repositório que incluam a P2; o manifesto local deste pacote só cobre a árvore entregue.
6. Rode os gates descritos na seção 8.

## 6. O que ainda precisa ser corrigido/verificado FORA da P2

### 6.1 P0 — inconsistência preexistente de manifesto

No `New Version.zip` original existe uma divergência de tamanho/hash em:

`phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1/tests/global/test_canonical_authority_binding.py`

Isso já existia antes desta P2 e não deve ser “corrigido” alterando a P2.
O agente integrador deve escolher uma das duas ações corretas:

- restaurar o arquivo que corresponde ao manifesto canônico da P0; ou
- se o arquivo atual for a versão correta/autorizada, regenerar o manifesto da P0 e toda evidência/hashes dependentes conforme a governança do projeto.

Depois rode o auditor de manifests novamente.

### 6.2 Manifests globais e release envelope

Ao inserir esta P2 no projeto completo:

- regenerar manifests globais que endereçam conteúdo;
- atualizar hashes de release/envelope dependentes;
- não reutilizar evidência de um snapshot anterior como se validasse o novo snapshot.

### 6.3 P1 / adapters de APIs externas

P2 não chama APIs. P1 deve preservar metadata suficiente para P2:

- provider e dataset/endpoint family;
- request ID / request params hash;
- retrieved_at / provider timestamp / declared available_at;
- timezone e frequência;
- pagination_complete / truncation_flag / warnings;
- feed type (ex.: OPRA vs indicative);
- price adjustment policy (RAW/SPLIT_ADJUSTED/TOTAL_RETURN_ADJUSTED/UNKNOWN);
- revision/vintage metadata quando aplicável;
- raw artifact path, size e SHA-256.

Se um provider novo for adicionado, prefira um adapter P1 para o envelope existente em vez de adicionar input obrigatório à P2.

### 6.4 Regras específicas de dados que devem ser conferidas

- séries macro revisáveis: confirmar vintage/knowledge-time;
- corporate actions: confirmar se o provider já entrega preços ajustados para impedir double-adjustment;
- opções: confirmar multiplier/deliverable/adjustment code em contratos ajustados;
- calendários: fornecer calendar/exchange quando houver múltiplos mercados no mesmo dia;
- feeds indicativos/delayed: preservar `feed_type` para quality/liquidity.

## 7. Pontos de manutenção por módulo

| Módulo | Responsabilidade final | Não quebrar | Principal ponto de manutenção |
|---|---|---|---|
| S1.M01 | validar chain of custody | 7 inputs e bundle output | novos campos P1 devem ser aditivos |
| S1.M02 | materializar raw físico | `raw_artifact_read_bundle` | escala de arquivos grandes / engines Parquet |
| S1.M03 | source quality | campos legados de score/status | calibrar policy sem esconder reasons |
| S2.M01 | temporal/PIT | `available_at` ISO e cutoff causal | policies por dataset/timezone |
| S2.M02 | identidade/domínio | `contract_key` público opaco | symbol mappings e novos asset classes |
| S3.M01 | macro BR/US | nomes dos dois outputs | revisions/frequency/unit |
| S3.M02 | benchmarks | grain público | aliases/currency/provider transitions |
| S3.M03 | calendário | output/grain aceito por P4/P6 | multi-market sessions/early close |
| S3.M04 | corporate actions | output legado | tipos novos e deliverables complexos |
| S3.M05 | underlying | `underlying+date` público | política de ajuste; OHLC não é reescrito silenciosamente |
| S3.M06 | tradability | `tradability_flag` | distinguir mercado aberto de readiness de execução |
| S4.M01 | contratos opção | `contract_key` público | multiplier/adjustment/deliverable |
| S4.M02 | quotes | quote→contract exato | stale threshold e provider priority |
| S4.M03 | custo/liquidez | outputs existentes | calibrar scores sem confundir com fill/slippage real |
| S5.M01 | contexto/docs/events | 3 outputs | retention/licensing e availability de notícias |
| S6.M01 | quality gate | `quality_report_phase_2` | severidade de novos checks |
| S6.M02 | handoffs | 4 manifests e targets | nunca embutir payload oculto no manifest |

## 8. Gates obrigatórios após integração

### Gate A — superfície

- 6/6 subfases;
- 17/17 módulos;
- 7/7 inputs;
- 20/20 outputs;
- grafo e nomes sem mudança.

### Gate B — P2

Rode todos os testes da P2 no monorepo, pois alguns testes são deliberadamente de fronteira e importam P3/P4/P6.

### Gate C — consumidores diretos

- P1 regression;
- P3;
- P4;
- P6.

### Gate D — downstream

- P5;
- P7;
- P8;
- P9.

### Gate E — mini-run físico

Use snapshot físico pequeno com SHA-256 real e atravesse os 17 módulos sem mocks entre subfases.

### Gate F — integridade

- compile/import;
- forbidden fields;
- network independence da P2;
- manifesto local;
- manifests globais após substituição;
- determinismo com mesmos inputs/config/seeds.

## 9. Interpretação correta de WARN

WARN não significa necessariamente falha.
Exemplo: se o underlying possui preço de referência, mercado aberto e fonte válida, mas não há bid/ask, P2 não inventa quote.
Nesse caso:

- `market_tradable_flag` pode ser verdadeiro;
- `execution_data_ready` é falso;
- P6 pode receber readiness WARN e decidir conservadoramente.

Isso é superior a transformar ausência de quote em spread zero.

## 10. Regras para futuras alterações

- não alterar contratos públicos unilateralmente;
- qualquer novo campo deve ser preferencialmente aditivo;
- consumidores não devem parsear `contract_key`;
- não duplicar parser temporal ou option identity em novas subfases;
- não adicionar chamadas de API à P2;
- não transformar UNKNOWN em valor otimista;
- não criar fixture magic dentro de código produtivo;
- atualizar testes semânticos e manifests após qualquer mudança.

## 11. Estado da documentação de qualification

`MASTER_PHASE_TEST_SPEC.yaml` é mantido como especificação histórica de pré-implementação/governança. Ele não concede autorização de produção.
A evidência técnica desta entrega está em:

- `qualification/P2_RELEASE_VALIDATION_SUMMARY.json`
- `qualification/P2_INTEGRATION_COMPATIBILITY_REPORT.md`
- `qualification/P2_MODULE_BY_MODULE_COMPARISON.csv`

A integração no projeto completo deve atualizar o estado global somente através do processo de governança/autorização do projeto; não é função deste ZIP alterar `PROJECT_STATE.json` global.
