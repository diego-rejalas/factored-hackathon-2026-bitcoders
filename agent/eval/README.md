# Evaluation

Code, case sets and results of the evaluation. The report, with the figures and their limits, is in
[`docs/EVALUATION.md`](../../docs/EVALUATION.md). This file covers how to repeat it.

```
eval/
  datasets/    the cases (invented by the team, labeled as such)
  results/     one line per case and a summary per run: every number in the report is recomputed from here
  stats.py     Wilson intervals, the exact McNemar test, percentiles, confusion matrix
  fixture.py   invented customers and transactions, with a seed, and the policy restated as the oracle
  generate_intent_set.py   the blind intent set (written by a model that is not the classifier)
  generate_policy_set.py   the end-to-end cases, derived from the fixture
  run_intent.py            component: keywords against model
  run_policy.py            system: the configuration without a model against the one with a model
```

## Repeating it

You need the local stack (`docker compose -f docker-compose.dev.yml up -d --build`), an OpenRouter key and the
same `SESSION_JWT_SECRET` as the compose file.

```bash
cd agent
python -m eval.fixture --load                                  # evaluation customers in the local database
OPENROUTER_API_KEY=... OPENROUTER_MODEL=anthropic/claude-haiku-4.5 python -m eval.run_intent
SESSION_JWT_SECRET=... BANK_URL=http://localhost:8000 python -m eval.run_policy baseline
SESSION_JWT_SECRET=... BANK_URL=http://localhost:8000 OPENROUTER_API_KEY=... OPENROUTER_MODEL=anthropic/claude-haiku-4.5 python -m eval.run_policy system
```

The generators (`generate_*`) were run once and their files are versioned. Running them again produces a different
set, not the same one. The evaluation's own tests (`tests/test_eval_*.py`) run with the rest of the suite.

The run empties and rebuilds `app.disputes` in the **local** database. Do not point it at a real one.
