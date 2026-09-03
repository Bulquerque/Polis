# Testes e Qualificação

## Matriz

A matriz reúne:

- suítes S1/S2 e integração histórica;
- suítes S3/S4;
- suíte S5/S6;
- suítes S7/S8;
- suítes S9/S10 e integração histórica;
- package-surface tests;
- adapters S1→S6;
- dual book S6→S8;
- evidence/runtime S8→S10.

## Golden threads presentes

1. candidato ranqueado chega de S1 até S6, mas termina sem nova exposição quando o risk state não o torna sizable;
2. transformação por candidato em targets físicos conserva o dual book;
3. S8 é transformada em evidence bundle S10 auditável;
4. comandos S9 são transformados em eventos aceitos por S7/S8;
5. replay e hashes são determinísticos nas suítes originais.

## O que os testes não provam

- vantagem econômica fora da amostra;
- calibração real com dados de mercado produtivos;
- consumer real da P9 vNext;
- autorização P0;
- execução live em broker;
- fidelidade exata de margem de uma clearing house específica.

Essas limitações impedem promoção produtiva, mas não impedem o fechamento técnico da integração RC0.
