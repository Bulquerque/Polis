# API and Data Compatibility

## B3 market history

A série histórica oficial da B3 é disponibilizada sem ajuste por inflação ou proventos. Consequentemente, a operação `get_history` usa `RAW` por padrão e não aplica ajuste retrospectivo sem uma superfície upstream explicitamente qualificada.

## Calendários

Calendários de negociação são versionados por ano e segmento. A V1 preserva datas observadas e não inventa dias úteis. Um adapter de calendário poderá ser adicionado no composition root sem alterar os contratos das operações.

## Opções

O manual de apreçamento da B3 emprega modelos, critérios de liquidez, taxas, seleção de séries e procedimentos de não arbitragem. A S36 V1 não tenta reproduzir essa autoridade. Ela expõe quotes e IV observadas e executa apenas diagnósticos descritivos.

## QuantLib e py_vollib

Ambos são referências úteis para adapters futuros: QuantLib oferece estruturas de termo, calendários e superfícies; py_vollib oferece preços, gregas e solução de IV. Nenhum é necessário para o baseline e nenhum será usado como fallback silencioso.
