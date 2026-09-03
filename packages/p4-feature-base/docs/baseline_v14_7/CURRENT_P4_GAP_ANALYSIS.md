# Análise da P4 RC4.1 e justificativa da reforma

## Diagnóstico

A RC4.1 possui uma boa fronteira conceitual — features point-in-time sem previsão — mas sua decomposição é insuficiente para a implementação pretendida.

### P4.S1 antiga

Validação de handoff, temporalidade, integração multimodal e feature bus aparecem no mesmo bloco. Isso impede que erros de vintage, calendário, entidade e missingness sejam fechados antes da construção de features.

### P4.S2 antiga

Mistura modalidades (`price`, `macro`, `social`), fenômenos (`momentum`, `reversion`, `risk`), estruturas (`pairs`, `clusters`) e técnicas (`entropy`, `correlation`). Adicionar mais módulos dentro dessa subfase aumentaria a lista, mas não resolveria a mistura de autoridades.

### P4.S3 antiga

Um único módulo pretende executar normalização, winsorization e interações. Cada operação exige estados de fit, políticas temporais, testes e lineage próprios.

### P4.S4 antiga

Seleção, PCA e embeddings são três classes diferentes de problema. A documentação também não separa seleção estrutural sem labels, permitida na P4, de seleção supervisionada, pertencente à P5.

### P4.S5 antiga

Lineage, drift, quality gate e handoff estão concentrados. O consumidor P5 não emite recibo material, então a integração pode parecer concluída sem prova de consumo.

## Por que suplementos não bastam

Suplementos seriam adequados se faltassem apenas novas famílias de features. O problema é mais profundo: faltam camadas de autoridade entre entrada, tempo, observação, interpretação, fusão, fit, representação e promoção.

## Critério usado para criar uma subfase

Uma responsabilidade virou subfase quando possui simultaneamente:

1. estado ou contratos próprios;
2. falhas que devem bloquear antes da etapa seguinte;
3. testes e oracles específicos;
4. possibilidade de evolução independente;
5. autoridade que não deve ser absorvida por outro bloco.

Aplicando esse critério, nove subfases são necessárias e suficientes. Mais do que isso criaria fragmentação; menos do que isso recriaria os monólitos antigos.
