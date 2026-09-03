# Applied Foundations

## B3 historical quotes

A documentação oficial informa que a série histórica mantém preços na moeda e forma de cotação da época, sem ajuste por inflação ou proventos. Aplicação: `RAW` é o único modo habilitado sem evidência upstream adicional.

## B3 options methodology

O manual de apreçamento da B3 mostra que produção de preços e superfícies envolve modelos, liquidez, taxas, seleção de séries, incertezas e critérios de não arbitragem. Aplicação: S36 V1 não declara equivalência com o apreçamento oficial; usa somente observações e diagnósticos limitados.

## QuantLib BlackVarianceSurface

A implementação de referência constrói uma superfície de variância a partir de matriz de volatilidades observadas e aplica interpolação configurável. Aplicação: interpolação é uma responsabilidade separada e fica desligada na V1.

## py_vollib

A biblioteca oferece preços, gregas e solução de volatilidade implícita. Aplicação: possível adapter futuro; não é dependência obrigatória.

## Arbitrage-free SVI

A literatura de SVI sem arbitragem mostra que uma superfície ajustada exige restrições e calibração cuidadosas. Aplicação: a V1 apenas detecta violações aparentes e não calibra SVI.
