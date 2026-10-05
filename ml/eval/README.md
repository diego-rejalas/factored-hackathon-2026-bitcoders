# ml/eval — sets retenidos y evaluación de los componentes ML

Sets **generados por el equipo**, sintéticos, sin PII y **sin columnas de
fraude** (`is_fraud`/`fraud_score` se eliminan y el generador lo verifica).
Rotulados como pide el reto (doc línea 54): la evaluación de un componente
preentrenado exige etiquetas propias, prevención de fuga y set retenido.

| archivo | componente | contenido |
|---|---|---|
| `data/intent_set.jsonl` | A: intención + idioma | 840 mensajes (720 normales, 60 por celda intent×idioma; 120 adversarios: inyección, ambigüedad, typos, trampas). Splits dev/test estratificados (20/40 por celda). 10% marcado `review_sample` para doble revisión manual. |
| `data/dispute_set.jsonl` | B: transacción disputada | 399 casos: reclamo con ruido controlado → etiqueta = `transaction_id` (o None en 40 casos `unrelated` que miden el "no encuentra"). **Split por cliente**: train y test no comparten clientes. Pool de transacciones sintético con las distribuciones medidas (estados 92/5/2/1, merchant nulo 76,7%, `amount_usd_effective` nulo ~57%, USD/COP/ARS, ventana 90 días al corte 2026-06-18). |

Reproducir:

```bash
python3 ml/eval/gen_intent_set.py          # semilla 20261004, determinista
python3 ml/eval/gen_dispute_set.py         # idem; --source duckdb:<ruta> o --source postgres para pool real
uv venv .venv && uv pip install scikit-learn pandas numpy httpx pytest
.venv/bin/python -m pytest ml/eval/test_eval_cost.py
.venv/bin/python ml/eval/eval_intent.py --split test --candidate all --final
.venv/bin/python ml/eval/eval_ranker.py  --split test --final
```

El candidato LLM del componente A necesita `OPENROUTER_API_KEY`
(clasificación estructurada, temperatura 0, 3 corridas para variabilidad):

```bash
OPENROUTER_API_KEY=... .venv/bin/python ml/eval/eval_intent.py --split test --candidate llm --runs 3 --final
```

El costo se calcula por llamada desde `usage.cost` cuando OpenRouter lo
devuelve. Si no está disponible, se puede estimar con tarifas por millón de
tokens, **solo con un modelo fijado** (`--model`) y ambas variables definidas:

```bash
OPENROUTER_API_KEY=... \
INTENT_EVAL_INPUT_PRICE_PER_1M_USD=... \
INTENT_EVAL_OUTPUT_PRICE_PER_1M_USD=... \
.venv/bin/python ml/eval/eval_intent.py --split test --candidate llm --model proveedor/modelo --runs 3 --final
```

Sin costo del proveedor ni ambas tarifas para el modelo fijado, el informe deja
costo p50/p95 como **N/A** (no imputa precios). El costo LLM de esta entrega
queda pendiente porque no había clave ni tarifas en el entorno.

Estado de la evaluación (2026-10-04):

- **Baseline del componente A medido** en dev y test (ver
  `reports/intent_eval.md`); LLM y embeddings quedan como comandos listos,
  pendientes de la clave del equipo (riesgo previsto en el plan).
- **Componente B medido completo** (baseline vs weighted vs GBM) en
  `reports/ranker_eval.md`; decisión de integración: el ranker weighted
  (stdlib) **solo ordena** el pool ambiguo en `agent/app/ranking.py`.
- Umbrales: el de abstención de intención (`INTENT_MIN_CONFIDENCE`, default
  0.5 por `DISPUTE_WORKFLOW` §4) y el piso de "no encuentra" del ranker se
  calibran con `--split dev` / `--split train`; **el test nunca los ajusta**.
- Pendiente humano: la muestra `review_sample` del set de intención (84 casos)
  está generada para doble revisión manual; el verificador automático
  (segundo léxico independiente) ya corrió y su acuerdo queda en el informe.
