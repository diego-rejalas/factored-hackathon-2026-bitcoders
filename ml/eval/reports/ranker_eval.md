# Evaluación del componente B: ranking de la transacción disputada

Split: **test** de `ml/eval/data/dispute_set.jsonl` (generado por el equipo; split por cliente, sin columnas de fraude).

| candidato | top-1 | top-3 | no-encuentra (unrelated) | vacíos falsos |
|---|---|---|---|---|
| baseline | 0.2588 | 0.2765 | 0.8696 | 0.5824 |
| weighted | 0.5588 | 0.9 | 0.0 | 0.0059 |
| gbm | 0.7294 | 0.9 | 0.6087 | 0.0588 |

## weighted

- umbral 'no encuentra' elegido en dev: 0.1
- top-1 por tipo de ruido: {'amount_off': 0.375, 'amount_vague': 0.7826, 'combo': 0.5, 'date_vague': 0.2424, 'merchant_missing': 0.5882, 'merchant_misspelled': 1.0}
- top-1 por moneda: {'ARS': 0.6774, 'COP': 0.6222, 'USD': 0.4894}
- sobre los pools del baseline: 1→0.7826, 2+→0.72, vacío→0.4141
- **reordenando el pool del baseline (integración 'ordena, no autoriza')**: pool=1 n=46 top-1 0.9348; pool 2+ n=25 top-1 **0.6**

## gbm

- umbral 'no encuentra' elegido en dev: 0.1
- top-1 por tipo de ruido: {'amount_off': 0.6562, 'amount_vague': 0.8261, 'combo': 0.8182, 'date_vague': 0.3939, 'merchant_missing': 0.8529, 'merchant_misspelled': 0.9231}
- top-1 por moneda: {'ARS': 0.8065, 'COP': 0.7333, 'USD': 0.7021}
- sobre los pools del baseline: 1→0.8696, 2+→0.64, vacío→0.6869
- **reordenando el pool del baseline (integración 'ordena, no autoriza')**: pool=1 n=46 top-1 0.9348; pool 2+ n=25 top-1 **0.6**

## Fallos incluidos

`ml/eval/reports/ranker_failures_test_<candidato>.jsonl` reúne los casos fuera del top-3 de cada ranker con el claim, la etiqueta y el tamaño del pool del baseline.
