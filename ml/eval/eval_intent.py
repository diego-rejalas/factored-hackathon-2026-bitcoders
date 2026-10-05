"""Evaluación del componente A: intención + idioma con confianza y abstención.

Candidatos, todos sobre exactamente el mismo set retenido
(ml/eval/data/intent_set.jsonl, generado por el equipo — ver gen_intent_set.py):

- baseline: `app.intents.baseline_classify` + `app.intents.baseline_language`,
  el camino de producción (palabras clave + substring es/pt). Sin confianza.
- llm: clasificación estructurada OpenRouter (`LLM.classify_detailed`),
  temperatura 0, salida JSON {intent, language, confidence}. Sin clave se
  degrada: se omite y el informe lo registra.
- embeddings (opcional): clasificador ligero sobre embeddings multilingües
  locales; se omite si sentence-transformers no está instalado.

Metodología (requisitos del reto, doc líneas 54 y 68):
- El umbral de abstención se elige SOLO en dev con costo asimétrico
  (falso auto-resolver cuesta 5; escalar de más cuesta 1). El split test se
  corre una vez congelado el umbral (--final) y no lo ajusta nada.
- Métricas: accuracy y macro-F1 por intención y por idioma; recall de
  out_of_scope; captura de manipulación; falsos "dispute"; ECE de la
  confianza; latencia y costo p50/p95; variabilidad en 3 corridas; fallos
  incluidos en el informe.

Uso:
    python ml/eval/eval_intent.py --split dev                       # ajuste de umbral
    python ml/eval/eval_intent.py --split test --final              # informe congelado
    OPENROUTER_API_KEY=... python ml/eval/eval_intent.py --candidate llm --runs 3

Cost fallback (when OpenRouter omits usage.cost): pin --model and provide
INTENT_EVAL_INPUT_PRICE_PER_1M_USD and INTENT_EVAL_OUTPUT_PRICE_PER_1M_USD
for that model. Without provider cost or both rates, cost is reported as N/A.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))

from app.intents import baseline_classify, baseline_language

INTENTS = ("dispute", "case_status", "greeting", "out_of_scope")
LANGUAGES = ("es", "pt", "mixto")
FALSE_AUTORESOLVE_COST = 5.0  # falso "dispute" con confianza para actuar
OVERESCALATION_COST = 1.0     # abstenerse cuando la etiqueta era correcta
TAU_GRID = [round(0.05 * i, 2) for i in range(1, 20)]

REPORTS = Path(__file__).parent / "reports"


def percentile(values: list, q: float) -> float:
    """Return the rounded nearest-rank percentile for ``q``."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[k]


def prf1(true_rows: list, pred_rows: list, label: str) -> dict:
    """Calculate precision, recall, F1, and support for one label."""
    tp = sum(1 for t, p in zip(true_rows, pred_rows) if t == label and p == label)
    fp = sum(1 for t, p in zip(true_rows, pred_rows) if t != label and p == label)
    fn = sum(1 for t, p in zip(true_rows, pred_rows) if t == label and p != label)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "support": tp + fn}


def macro_f1(true_rows: list, pred_rows: list, labels: tuple) -> float:
    """Calculate the unweighted mean of per-label F1 scores."""
    return round(statistics.fmean(prf1(true_rows, pred_rows, l)["f1"] for l in labels), 4)


def ece(confidences: list, correct: list, bins: int = 10) -> float:
    """Calculate expected calibration error using equal-width bins."""
    pairs = [(c, ok) for c, ok in zip(confidences, correct) if c is not None]
    if not pairs:
        return float("nan")
    total = len(pairs)
    error = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bucket = [(c, ok) for c, ok in pairs if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not bucket:
            continue
        error += len(bucket) / total * abs(statistics.fmean(ok for _, ok in bucket) - statistics.fmean(c for c, _ in bucket))
    return round(error, 4)


# ----------------------------------------------------------------- candidatos

def run_baseline(cases: list) -> list[dict]:
    """Run the production keyword and substring-language baseline."""
    rows = []
    start = time.monotonic()
    for case in cases:
        t0 = time.perf_counter()
        intent = baseline_classify(case["text"])
        language = baseline_language(case["text"])
        rows.append({
            "case_id": case["case_id"], "intent": intent, "language": language,
            "confidence": None, "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
        })
    rows.append({"_meta": {"wall_ms": round((time.monotonic() - start) * 1000)}})
    return rows


def call_cost_usd(usage: dict, requested_model: str | None,
                  actual_model: str | None) -> tuple[float | None, str]:
    """Return provider-reported or configured per-call cost in USD.

    Use OpenRouter's ``usage.cost`` when available. The environment-rate
    fallback is valid only when an exact model is pinned with ``--model``.
    """
    try:
        provider_cost = usage.get("cost")
        if provider_cost is not None and float(provider_cost) >= 0:
            return round(float(provider_cost), 10), "openrouter_usage.cost"
    except (TypeError, ValueError):
        pass

    if not requested_model or requested_model != actual_model:
        return None, "unavailable: pin --model or use OpenRouter usage.cost"
    try:
        input_rate = float(os.environ["INTENT_EVAL_INPUT_PRICE_PER_1M_USD"])
        output_rate = float(os.environ["INTENT_EVAL_OUTPUT_PRICE_PER_1M_USD"])
        input_tokens = int(usage["prompt_tokens"])
        output_tokens = int(usage["completion_tokens"])
    except (KeyError, TypeError, ValueError):
        return None, "unavailable: provider cost or both per-million rates required"
    if min(input_rate, output_rate, input_tokens, output_tokens) < 0:
        return None, "unavailable: prices and token counts must be non-negative"
    cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    return round(cost, 10), "configured_per_million_rates"


async def run_llm(cases: list, model: str | None, concurrency: int = 8) -> list[dict]:
    """Evaluate structured OpenRouter classification for each case."""
    from app.llm import LLM

    llm = LLM(api_key=None)  # la clave viene de OPENROUTER_API_KEY
    if model:
        llm.models = [model]
    if not llm.enabled:
        return [{"_meta": {"skipped": "sin OPENROUTER_API_KEY"}}]
    sem = asyncio.Semaphore(concurrency)
    errors = 0

    async def one(case: dict) -> dict:
        nonlocal errors
        async with sem:
            detail = await llm.classify_detailed(case["text"])
        if detail is None:
            errors += 1
            return {"case_id": case["case_id"], "intent": None, "language": None,
                    "confidence": None, "latency_ms": None, "cost_usd": None,
                    "error": "sin respuesta válida"}
        usage = detail.get("usage") or {}
        cost, cost_source = call_cost_usd(usage, model, detail.get("model"))
        return {
            "case_id": case["case_id"], "intent": detail["intent"],
            "language": detail["language"], "confidence": detail["confidence"],
            "model": detail["model"], "latency_ms": detail["latency_ms"],
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "cost_usd": cost, "cost_source": cost_source,
        }

    rows = await asyncio.gather(*(one(c) for c in cases))
    models = Counter(r.get("model") for r in rows if r.get("model"))
    meta = {"model": dict(models), "requested_model": model,
            "prompt_version": "v1-2026-10-04",
            "temperature": 0.0, "errors": errors}
    return list(rows) + [{"_meta": meta}]


def run_embeddings(cases: list, train_cases: list) -> list[dict]:
    """Train and evaluate an optional multilingual embedding classifier."""
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        return [{"_meta": {"skipped": "sentence-transformers/sklearn no instalado"}}]
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    Xtr = model.encode([c["text"] for c in train_cases], show_progress_bar=False)
    clf = LogisticRegression(max_iter=2000).fit(Xtr, [c["intent"] for c in train_cases])
    X = model.encode([c["text"] for c in cases], show_progress_bar=False)
    proba = clf.predict_proba(X)
    labels = list(clf.classes_)
    rows = []
    for case, row in zip(cases, proba):
        best = max(range(len(labels)), key=lambda i: row[i])
        rows.append({"case_id": case["case_id"], "intent": labels[best],
                     "language": baseline_language(case["text"]),
                     "confidence": round(float(row[best]), 4)})
    rows.append({"_meta": {"model": "paraphrase-multilingual-MiniLM-L12-v2 + LogisticRegression"}})
    return rows


# ------------------------------------------------------------------- métricas

def score(rows: list, cases: list, threshold: float | None) -> tuple[dict, list]:
    """Calculate classification, safety, language, calibration, and latency metrics."""
    meta = next((r["_meta"] for r in rows if "_meta" in r), {})
    preds = [r for r in rows if "case_id" in r]
    by_id = {c["case_id"]: c for c in cases}
    n = len(preds)
    true_int = [by_id[r["case_id"]]["intent"] for r in preds]
    pred_int = [r["intent"] for r in preds]
    conf = [r.get("confidence") for r in preds]

    acted = [conf[i] is not None and conf[i] >= threshold for i in range(n)] if threshold is not None else [True] * n
    correct = [true_int[i] == pred_int[i] for i in range(n)]
    manipulation = [by_id[r["case_id"]]["manipulation"] for r in preds]
    ambiguous = [by_id[r["case_id"]]["ambiguous"] for r in preds]

    unsafe = sum(1 for i in range(n) if acted[i] and pred_int[i] == "dispute"
                 and (true_int[i] != "dispute" or manipulation[i]))
    abstained_ok = sum(1 for i in range(n) if not acted[i] and correct[i])
    abstained_bad = sum(1 for i in range(n) if not acted[i] and not correct[i])

    def abstain_cost(tau: float) -> float:
        act = [conf[i] is not None and conf[i] >= tau for i in range(n)]
        bad_action = sum(1 for i in range(n) if act[i] and pred_int[i] == "dispute"
                         and (true_int[i] != "dispute" or manipulation[i]))
        extra_escalation = sum(1 for i in range(n) if not act[i] and correct[i] and not manipulation[i])
        return FALSE_AUTORESOLVE_COST * bad_action + OVERESCALATION_COST * extra_escalation

    result = {
        "n": n,
        "meta": meta,
        "accuracy": round(statistics.fmean(correct), 4),
        "macro_f1_intent": macro_f1(true_int, pred_int, INTENTS),
        "per_intent": {l: prf1(true_int, pred_int, l) for l in INTENTS},
        "out_of_scope_recall": prf1(true_int, pred_int, "out_of_scope")["recall"],
        "false_dispute": sum(1 for i in range(n) if pred_int[i] == "dispute" and true_int[i] != "dispute"),
        "manipulation_caught": round(statistics.fmean(
            pred_int[i] != "dispute" for i in range(n) if manipulation[i]), 4) if any(manipulation) else None,
        "ambiguous_abstained_or_wrong_intent": round(statistics.fmean(
            pred_int[i] != "dispute" for i in range(n) if ambiguous[i]), 4) if any(ambiguous) else None,
        "ece": ece(conf, correct),
    }
    true_lang = [by_id[r["case_id"]]["language"] for r in preds]
    pred_lang = [r["language"] for r in preds]
    result["language_accuracy"] = {
        lang: round(statistics.fmean(pred_lang[i] == lang for i in range(n) if true_lang[i] == lang), 4)
        if any(true_lang[i] == lang for i in range(n)) else None
        for lang in LANGUAGES
    }
    if threshold is not None:
        result["threshold"] = threshold
        result["abstention_rate"] = round(statistics.fmean(not a for a in acted), 4)
        result["unsafe_auto_resolve"] = unsafe
        result["abstained_when_correct"] = abstained_ok
        result["abstained_when_wrong"] = abstained_bad
        result["abstention_cost_dev_curve"] = {str(t): round(abstain_cost(t), 1) for t in TAU_GRID}
    latencies = [r["latency_ms"] for r in preds if r.get("latency_ms") is not None]
    result["latency_ms"] = {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)} if latencies else None
    tokens_in = [r["input_tokens"] for r in preds if r.get("input_tokens")]
    tokens_out = [r["output_tokens"] for r in preds if r.get("output_tokens")]
    if tokens_in:
        result["tokens"] = {
            "input_p50": percentile(tokens_in, 0.5), "input_p95": percentile(tokens_in, 0.95),
            "output_p50": percentile(tokens_out, 0.5), "output_p95": percentile(tokens_out, 0.95),
            "input_total": sum(tokens_in), "output_total": sum(tokens_out),
        }
    costs = [r["cost_usd"] for r in preds if r.get("cost_usd") is not None]
    if costs:
        sources = sorted({r.get("cost_source") for r in preds if r.get("cost_usd") is not None})
        result["cost_usd"] = {
            "status": "measured", "p50": percentile(costs, 0.5),
            "p95": percentile(costs, 0.95), "total": round(sum(costs), 10),
            "measured_calls": len(costs), "sources": sources,
        }
    elif "prompt_version" in meta:
        result["cost_usd"] = {
            "status": "not_measured", "p50": None, "p95": None, "total": None,
            "reason": "no provider-reported cost and no matching pinned-model rates",
        }
    else:
        result["cost_usd"] = {"status": "not_applicable", "p50": None, "p95": None, "total": None}
    failures = [
        {"case_id": preds[i]["case_id"], "text": by_id[preds[i]["case_id"]]["text"],
         "true": true_int[i], "pred": pred_int[i], "confidence": conf[i],
         "language_true": true_lang[i], "language_pred": pred_lang[i],
         "adversary": by_id[preds[i]["case_id"]]["adversary"]}
        for i in range(n) if not correct[i]
    ]
    return result, failures


def choose_threshold(dev_result: dict) -> float:
    """Select the minimum-cost abstention threshold from the dev curve."""
    curve = dev_result["abstention_cost_dev_curve"]
    return min(TAU_GRID, key=lambda t: curve[str(t)])


# ---------------------------------------------------------------------- main

async def async_main(args) -> None:
    """Run selected candidates and save metrics and failure examples."""
    data = [json.loads(line) for line in
            (Path(__file__).parent / "data" / "intent_set.jsonl").open(encoding="utf-8")]
    cases = [c for c in data if c["split"] == args.split]
    train_cases = [c for c in data if c["split"] == "dev"]
    print(f"split {args.split}: {len(cases)} casos "
          f"({Counter(c['intent'] for c in cases)}, {Counter(c['language'] for c in cases)})")

    candidates: dict[str, list] = {}
    if args.candidate in ("baseline", "all"):
        candidates["baseline"] = run_baseline(cases)
    if args.candidate in ("llm", "all"):
        for run in range(1, args.runs + 1):
            print(f"llm corrida {run}/{args.runs}...")
            rows = await run_llm(cases, args.model)
            if rows and rows[-1].get("_meta", {}).get("skipped"):
                print("llm omitido:", rows[-1]["_meta"]["skipped"])
                break
            candidates[f"llm_run{run}"] = rows
    if args.candidate in ("embeddings", "all"):
        candidates["embeddings"] = run_embeddings(cases, train_cases)

    threshold = args.threshold
    dev_curve = None
    if threshold is None and any(k.startswith("llm") or k == "embeddings" for k in candidates):
        # El umbral se calibra en dev: corrdenada del costo asimétrico mínimo.
        dev_cases = [c for c in data if c["split"] == "dev"]
        key = next(k for k in candidates if k.startswith("llm") or k == "embeddings")
        dev_rows = candidates[key]
        if not dev_rows or "_meta" not in dev_rows[-1] or not dev_rows[-1]["_meta"].get("skipped"):
            if key.startswith("llm"):
                dev_rows = (await run_llm(dev_cases, args.model)) if args.split != "dev" else candidates[key]
            else:
                dev_rows = run_embeddings(dev_cases, dev_cases)
            dev_result, _ = score(dev_rows, dev_cases, threshold=0.5)
            dev_curve = dev_result["abstention_cost_dev_curve"]
            threshold = min(TAU_GRID, key=lambda t: dev_curve[str(t)])
            print(f"umbral de abstención elegido en dev: {threshold} (costo {dev_curve[str(threshold)]})")

    REPORTS.mkdir(parents=True, exist_ok=True)
    results: dict = {"split": args.split, "threshold": threshold, "candidates": {}}
    all_failures: dict[str, list] = {}
    for name, rows in candidates.items():
        result, failures = score(rows, cases, threshold=threshold)
        if rows and rows[-1].get("_meta", {}).get("skipped"):
            results["candidates"][name] = {"skipped": rows[-1]["_meta"]["skipped"]}
            continue
        results["candidates"][name] = result
        all_failures[name] = failures

    if dev_curve:
        results["dev_threshold_curve"] = dev_curve

    # variabilidad entre corridas LLM
    llm_runs = [k for k in candidates if k.startswith("llm_run")]
    if len(llm_runs) >= 2:
        accs = [round(results["candidates"][k]["accuracy"], 4) for k in llm_runs]
        f1s = [results["candidates"][k]["macro_f1_intent"] for k in llm_runs]
        results["variability"] = {
            "runs": len(llm_runs), "accuracy": accs,
            "accuracy_range": [min(accs), max(accs)], "macro_f1": f1s,
        }

    out_json = REPORTS / f"intent_results_{args.split}.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, failures in all_failures.items():
        fpath = REPORTS / f"intent_failures_{args.split}_{name}.jsonl"
        with fpath.open("w", encoding="utf-8") as fh:
            for failure in failures:
                fh.write(json.dumps(failure, ensure_ascii=False) + "\n")
        print(f"fallos {name}: {len(failures)} -> {fpath.name}")
    print(f"resultados: {out_json}")

    if args.final:
        write_report(results, args)
        print(f"informe: {REPORTS / 'intent_eval.md'}")
    else:
        for name, result in results["candidates"].items():
            if "skipped" in result:
                print(name, "OMITIDO:", result["skipped"])
                continue
            print(f"\n== {name} ==")
            for key in ("accuracy", "macro_f1_intent", "out_of_scope_recall", "false_dispute",
                        "manipulation_caught", "ece", "language_accuracy", "latency_ms"):
                print(f"  {key}: {result.get(key)}")
            if "unsafe_auto_resolve" in result:
                print(f"  umbral={result['threshold']} abstención={result['abstention_rate']} "
                      f"auto-resolución insegura={result['unsafe_auto_resolve']} "
                      f"abstenido-correcto={result['abstained_when_correct']}")


def write_report(results: dict, args) -> None:
    """Write the Markdown evaluation report for a completed split."""
    split = results["split"]
    lines = [
        "# Evaluación del componente A: intención + idioma (set retenido generado por el equipo)",
        "",
        (f"Split: **{split}** de `ml/eval/data/intent_set.jsonl` "
         f"(generado con `gen_intent_set.py`, etiquetas válidas por construcción; "
         f"el test no se usó para ajustar prompts ni umbrales)."),
        (f"Umbral de abstención: **{results['threshold']}**, elegido en dev con costo asimétrico "
         f"(falso auto-resolver = {FALSE_AUTORESOLVE_COST:.0f}, escalar de más = {OVERESCALATION_COST:.0f})."),
        "",
    ]
    if "dev_threshold_curve" in results:
        lines += ["Curva de costo en dev:", "",
                  "| umbral | costo |", "|---|---|"]
        lines += [f"| {t} | {c} |" for t, c in results["dev_threshold_curve"].items()]
        lines.append("")
    for name, result in results["candidates"].items():
        if "skipped" in result:
            lines += [f"## {name}", "", f"OMITIDO: {result['skipped']}.",
                      "Costo USD p50/p95: N/A (el candidato no se ejecutó).", ""]
            continue
        lines += [f"## {name}", ""]
        meta = result.get("meta") or {}
        if meta.get("model"):
            lines += [(f"- Modelos: `{meta['model']}`, prompt `{meta.get('prompt_version')}`, "
                       f"temperatura {meta.get('temperature')}, errores {meta.get('errors')}.")]
        lines += [
            f"- n = {result['n']}, accuracy **{result['accuracy']}**, macro-F1 intención **{result['macro_f1_intent']}**",
            (f"- recall out_of_scope **{result['out_of_scope_recall']}**, falsos dispute {result['false_dispute']}, "
             f"manipulación capturada {result['manipulation_caught']}, ambiguo≠dispute {result['ambiguous_abstained_or_wrong_intent']}"),
            f"- ECE confianza: {result['ece']}",
            f"- idioma (accuracy por clase): {result['language_accuracy']}",
            f"- latencia ms p50/p95: {result['latency_ms'] and (result['latency_ms']['p50'], result['latency_ms']['p95'])}",
        ]
        if "tokens" in result:
            tokens = result["tokens"]
            lines.append(f"- tokens p50/p95 in/out: {tokens['input_p50']}/{tokens['input_p95']} / "
                         f"{tokens['output_p50']}/{tokens['output_p95']} (totales {tokens['input_total']}/{tokens['output_total']})")
        cost = result.get("cost_usd") or {"status": "not_measured"}
        if cost["status"] == "measured":
            lines.append(f"- costo USD p50/p95: {cost['p50']}/{cost['p95']} "
                         f"(total {cost['total']}; {cost['measured_calls']} llamadas; "
                         f"fuente {cost['sources']})")
        elif cost["status"] == "not_measured":
            lines.append(f"- costo USD p50/p95: N/A ({cost.get('reason', 'no medido')})")
        else:
            lines.append("- costo USD: no aplica (candidato local/determinista)")
        if "abstention_rate" in result:
            lines.append(f"- abstención {result['abstention_rate']}, auto-resolución insegura "
                         f"**{result['unsafe_auto_resolve']}**, abstenido-correcto {result['abstained_when_correct']}, "
                         f"abstenido-incorrecto {result['abstained_when_wrong']}")
        lines += ["", "| intención | precision | recall | f1 | soporte |", "|---|---|---|---|---|"]
        for intent, m in result["per_intent"].items():
            lines.append(f"| {intent} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
        lines.append("")
    if "variability" in results:
        v = results["variability"]
        lines += [f"## Variabilidad entre corridas (n={v['runs']})",
                  "", f"- accuracy por corrida: {v['accuracy']} (rango {v['accuracy_range']})",
                  f"- macro-F1 por corrida: {v['macro_f1']}", ""]
    lines += ["## Fallos incluidos", "",
              "Los fallos de cada candidato sobre este split están volcados en "
              "`ml/eval/reports/intent_failures_" + split + "_<candidato>.jsonl` "
              "(requisito del reto, doc línea 68) con texto, etiqueta verdadera, predicción, confianza y adversario."]
    (REPORTS / "intent_eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Parse command-line arguments and start the intent evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--candidate", choices=("baseline", "llm", "embeddings", "all"), default="baseline")
    parser.add_argument("--runs", type=int, default=3, help="corridas LLM para variabilidad")
    parser.add_argument("--model", default=None, help="modelo OpenRouter (default: OPENROUTER_MODEL o los de app.llm)")
    parser.add_argument("--threshold", type=float, default=None, help="fijar umbral (si no, se calibra en dev)")
    parser.add_argument("--final", action="store_true", help="escribe ml/eval/reports/intent_eval.md")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
