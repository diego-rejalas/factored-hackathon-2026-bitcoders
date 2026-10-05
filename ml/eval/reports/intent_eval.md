# Evaluación del componente A: intención + idioma (set retenido generado por el equipo)

Split: **test** de `ml/eval/data/intent_set.jsonl` (generado con `gen_intent_set.py`, etiquetas válidas por construcción; el test no se usó para ajustar prompts ni umbrales).
Umbral de abstención: **None**, elegido en dev con costo asimétrico (falso auto-resolver = 5, escalar de más = 1).

## baseline

- n = 552, accuracy **0.6812**, macro-F1 intención **0.6768**
- recall out_of_scope **0.7347**, falsos dispute 36, manipulación capturada 0.8889, ambiguo≠dispute 0.7778
- ECE confianza: nan
- idioma (accuracy por clase): {'es': 1.0, 'pt': 0.2826, 'mixto': 0.0}
- latencia ms p50/p95: (0.01, 0.015)
- costo USD: no aplica (candidato local/determinista)

| intención | precision | recall | f1 | soporte |
|---|---|---|---|---|
| dispute | 0.7483 | 0.723 | 0.7354 | 148 |
| case_status | 1.0 | 0.4526 | 0.6231 | 137 |
| greeting | 0.5756 | 0.825 | 0.6781 | 120 |
| out_of_scope | 0.6171 | 0.7347 | 0.6708 | 147 |

## Fallos incluidos

Los fallos de cada candidato sobre este split están volcados en `ml/eval/reports/intent_failures_test_<candidato>.jsonl` (requisito del reto, doc línea 68) con texto, etiqueta verdadera, predicción, confianza y adversario.
