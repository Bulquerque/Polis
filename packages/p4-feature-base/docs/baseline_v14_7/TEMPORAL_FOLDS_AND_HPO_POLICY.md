# Folds temporais e hiperparâmetros

## Representações P4

- outer folds cronológicos expansivos;
- fit termina antes do bloco transformado;
- representações históricas são out-of-fold;
- estados de fit são imutáveis e versionados;
- embargo é aplicado quando janelas ou labels downstream se sobrepõem.

## Parâmetros das features

Cada passaporte permite uma definição primária e, no máximo, uma robustez. Nenhum parâmetro é escolhido por retorno futuro na P4.

## Encoder

Duas configurações pré-registradas, sem random search amplo. Inner folds existem apenas para verificar estabilidade e early stopping; a avaliação final permanece separada.
