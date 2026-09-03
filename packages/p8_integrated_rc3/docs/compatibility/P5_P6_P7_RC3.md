# Compatibilidade P5–P7 RC3 → P8 RC2

## Escopo

A P8 RC2 aceita a publicação real do bundle `P5_P6_P7_COMPATIBILITY_HARDENED_RC3` por uma fronteira versionada:

```text
quant_pipeline.phase_08_portfolio_control.compatibility.p567_rc3
```

O bridge não modifica os modelos nativos de S1/S2 e não habilita parsing permissivo. Ele transforma artefatos RC3 em:

- `P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1`;
- `P6_CANDIDATE_ECONOMIC_PACKAGE_V1`;
- `P7_TO_P8_RANKING_HANDOFF_V1`;
- `BeliefRecord` empírico para S3;
- `P567_RC3_TO_P8_ADAPTATION_RECEIPT_V1`.

## Princípios

1. Os payloads RC3 permanecem evidência imutável em wrappers content-addressed.
2. O hash reportado pela origem é preservado, mas não é apresentado como hash dos bytes canônicos da P8.
3. Novos clocks P8 são criados; `available_at` da RC3 não é reutilizado com semântica diferente.
4. Scores internos da P7 são convertidos apenas em preferência `ORDINAL`.
5. O bridge nunca produz retorno esperado, probabilidade ou peso a partir do ranking.
6. `weakest_leg_liquidity` não é convertido em capacidade de contratos; a capacidade permanece `UNAVAILABLE`.
7. Maximum loss só é qualificado quando `maximum_loss_proven=true` e o valor está presente.
8. Opções com exercício/assignment `NOT_MODELLED` permanecem preservadas, mas lifecycle fica `UNAVAILABLE` e S2 não as encaminha.
9. Todos os candidatos recebidos precisam fechar exatamente em ranked + eligibility blocked + safety blocked + abstained.
10. Qualquer evidência econômica necessária ausente causa falha fechada.

## Uso

```python
from datetime import datetime, UTC
from quant_pipeline.phase_08_portfolio_control import adapt_p567_rc3_to_p8

adapted = adapt_p567_rc3_to_p8(
    p5_publication=p5_publication,
    p6_outputs=p6_outputs,
    p7_result=p7_full_result,
    p8_run_id="run-p8",
    p8_cycle_id="cycle-p8",
    p8_decision_time=datetime(..., tzinfo=UTC),
    market_cutoff_at=datetime(..., tzinfo=UTC),
    computed_at=datetime(..., tzinfo=UTC),
    recorded_at=datetime(..., tzinfo=UTC),
    available_at=datetime(..., tzinfo=UTC),
)

artifact_store = adapted.build_artifact_store()
p7_handoff_bytes = adapted.handoff_bytes
```

`available_at` do bridge deve ser anterior ou igual ao `decision_time` do consumidor P8. A ordem é:

```text
market cutoff
<= P7 source decision
<= bridge computed
<= bridge recorded
<= bridge available
<= P8 consumer decision
```

## Caminhos qualificados

### All-abstained

```text
P5 real → P6 real → P7 real (3 abstidos)
→ bridge RC3
→ S1 native
→ NO_ACTION_VALID
→ S2 preserva os três estados terminais
```

### Ranked

O bridge suporta registros RC3 ranqueados e publica P6/P5 nativos para cada candidato. A execução permanece fail-closed:

- underlying linear com payoff/lifecycle qualificados pode seguir para risco;
- opção sem lifecycle modelado é `STATIC_CAPABILITY_UNSUPPORTED`;
- confidence sem artefato de calibração content-addressed é `UNCALIBRATED`;
- score é sempre `ORDINAL`.

## Limites

A compatibilidade significa que os contratos atuais podem ser consumidos sem perda silenciosa nem invenção econômica. Não significa autorização produtiva. Continuam necessários:

- P9 vNext real;
- autorização P0;
- adapters de mercado/broker live;
- qualificação econômica prospectiva.
