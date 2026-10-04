# Evaluación

Código, conjuntos de casos y resultados de la evaluación. El informe, con las cifras y sus límites, está en
[`docs/EVALUATION.md`](../../docs/EVALUATION.md). Aquí, cómo repetirla.

```
eval/
  datasets/    los casos (inventados por el equipo, rotulados como tales)
  results/     una línea por caso y un resumen por corrida: todo número del informe se recalcula de aquí
  stats.py     intervalos de Wilson, prueba de McNemar exacta, percentiles, matriz de confusión
  fixture.py   clientes y transacciones inventados, con semilla, y la política restablecida como oráculo
  generate_intent_set.py   el conjunto ciego de intenciones (lo escribe un modelo que no es el clasificador)
  generate_policy_set.py   los casos de punta a punta, derivados del fixture
  run_intent.py            componente: palabras clave contra modelo
  run_policy.py            sistema: configuración sin modelo contra configuración con modelo
```

## Repetirla

Hace falta el stack local (`docker compose -f docker-compose.dev.yml up -d --build`), una clave de OpenRouter y la
misma `SESSION_JWT_SECRET` del compose.

```bash
cd agent
python -m eval.fixture --load                                  # clientes de evaluación en la base local
OPENROUTER_API_KEY=... OPENROUTER_MODEL=anthropic/claude-haiku-4.5 python -m eval.run_intent
SESSION_JWT_SECRET=... BANK_URL=http://localhost:8000 python -m eval.run_policy baseline
SESSION_JWT_SECRET=... BANK_URL=http://localhost:8000 OPENROUTER_API_KEY=... OPENROUTER_MODEL=anthropic/claude-haiku-4.5 python -m eval.run_policy system
```

Los generadores (`generate_*`) se corrieron una vez y sus archivos están versionados: volver a correrlos produce otro
conjunto, no el mismo. Las pruebas de la propia evaluación (`tests/test_eval_*.py`) corren con el resto de la suite.

La corrida vacía y reconstruye `app.disputes` de la base **local**; no la apuntes a una base real.
