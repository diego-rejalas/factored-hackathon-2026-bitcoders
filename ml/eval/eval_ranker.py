"""Evaluación del componente B: ranking de la transacción disputada.

Candidatos sobre exactamente el mismo set retenido
(ml/eval/data/dispute_set.jsonl, generado por el equipo — gen_dispute_set.py):

- baseline: `app.guardrail.narrow_candidates` + el orden de entrada, tal cual
  producción (determinista). top-1 = primera del pool reducido;
  "no encuentra" = pool vacío.
- weighted: suma ponderada interpretable (similitud de comercio con difflib +
  cercanía relativa de monto + cercanía de fecha + canal detectado en el
  reclamo). Umbral de "no encuentra" elegido en dev.
- gbm: HistGradientBoosting entrenado en train (split por cliente) con esas
  mismas features. Umbral de "no encuentra" elegido en dev.

Métricas (test): top-1 y top-3 sobre casos etiquetados, por tipo de ruido y
moneda; tasa de "no encuentra" correcta sobre casos `unrelated` (etiqueta
None) y vacíos falsos sobre casos etiquetados; vistas adicionales: subset
donde el baseline deja un pool de 1 (identificación) y donde deja 2+
(desambiguación). El baseline no consume fraude ni nada fuera del claim.

Uso:
    python ml/eval/eval_ranker.py --split train      # calibrar umbrales (clientes train)
    python ml/eval/eval_ranker.py --split test --final
"""

import argparse
import difflib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))

from app.guardrail import AMOUNT_RE, DAYS_RE, NOT_AMOUNT_RE, normalize, parse_number

REPORTS = Path(__file__).parent / "reports"
WEIGHTS = {"merchant": 0.40, "amount": 0.35, "date": 0.15, "channel": 0.10}
FLOOR_GRID = [round(0.05 * i, 2) for i in range(2, 15)]
CHANNEL_HINTS = {"atm": ("cajero", "caixa", "atm", "extracc", "saque"), "online": ("online", "internet", "web", "app")}


# -------------------------------------------------------------------- features

def claim_amount(claim: str) -> float | None:
    """Extract the largest numeric amount from a customer claim."""
    stripped = NOT_AMOUNT_RE.sub(" ", claim.lower())
    numbers = [parse_number(m.group(0)) for m in AMOUNT_RE.finditer(stripped)]
    return max(numbers) if numbers else None


def claim_days(claim: str) -> int | None:
    """Return the approximate relative date mentioned in a claim."""
    match = DAYS_RE.search(claim)
    if match:
        return int(next(g for g in match.groups() if g))
    low = normalize(claim)
    if "ayer" in low or "ontem" in low or "anteontem" in low:
        return 2
    if "semana passada" in low or "la semana pasada" in low:
        return 7
    if "começo do mês" in low or "principios de mes" in low:
        return 15
    return None


def claim_channel(claim: str) -> str | None:
    """Infer an ATM or online channel from claim wording."""
    low = normalize(claim)
    for channel, hints in CHANNEL_HINTS.items():
        if any(h in low for h in hints):
            return channel
    return None


def merchant_sim(claim: str, merchant: str | None) -> float:
    """Score fuzzy token overlap between a claim and merchant name."""
    if not merchant:
        return 0.0
    m = normalize(merchant)
    low = normalize(claim)
    if m in low:
        return 1.0
    # mejor token a token: el cliente suele escribir una parte del nombre
    best = 0.0
    for token in m.split():
        if len(token) >= 4:
            for word in low.replace(",", " ").replace(".", " ").split():
                ratio = difflib.SequenceMatcher(None, token, word).ratio()
                best = max(best, ratio)
    return best


def amount_feature(claim_amt: float | None, tx: dict) -> float:
    """Score relative distance from claim amount to transaction amounts."""
    if claim_amt is None or claim_amt <= 0:
        return 0.5  # neutro: sin monto no hay evidencia ni a favor ni en contra
    best = None
    for value in (tx.get("amount"), tx.get("amount_usd_effective")):
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        rel = abs(value - claim_amt) / max(claim_amt, 1.0)
        best = rel if best is None else min(best, rel)
    if best is None:
        return 0.2  # el monto del claim no se puede comparar con ninguna columna
    return max(0.0, 1.0 - min(1.0, best))


def date_feature(claim_days_value: int | None, tx: dict) -> float:
    """Score the transaction date against a relative date in the claim."""
    if claim_days_value is None:
        return 0.5
    try:
        from datetime import date

        tx_day = date.fromisoformat(str(tx["transaction_date"])[:10])
        tx_days = (date(2026, 6, 18) - tx_day).days  # corte del set, ver generador
    except (ValueError, KeyError, TypeError):
        return 0.5
    return max(0.0, 1.0 - min(1.0, abs(tx_days - claim_days_value) / 30.0))


def channel_feature(claim_ch: str | None, tx: dict) -> float:
    """Score agreement between the inferred and transaction channels."""
    if claim_ch is None or not tx.get("channel"):
        return 0.5
    return 1.0 if normalize(str(tx["channel"])) == claim_ch else 0.2


def features(claim: str, tx: dict) -> dict:
    """Return the four interpretable claim-to-transaction feature scores."""
    return {
        "merchant": merchant_sim(claim, tx.get("merchant_name")),
        "amount": amount_feature(claim_amount(claim), tx),
        "date": date_feature(claim_days(claim), tx),
        "channel": channel_feature(claim_channel(claim), tx),
    }


def weighted_score(claim: str, tx: dict) -> float:
    """Combine available feature scores using the fixed evaluation weights."""
    f = features(claim, tx)
    active = {k: v for k, v in f.items() if not (k in ("date", "channel") and v == 0.5)}
    # sin evidencia de fecha o canal, el peso se reparte entre las señales presentes
    weights = {k: WEIGHTS[k] for k in active}
    total = sum(weights.values()) or 1.0
    return sum(active[k] * weights[k] for k in active) / total


# ------------------------------------------------------------------ candidatos

def run_baseline(cases: list) -> list[dict]:
    """Run production narrowing and preserve its original candidate order."""
    from app.guardrail import extract_entities, narrow_candidates

    rows = []
    for case in cases:
        entities = extract_entities(case["claim"])
        pool = narrow_candidates(case["candidates"], case["claim"], entities)
        ranked = [tx["transaction_id"] for tx in pool]
        rows.append({"case_id": case["case_id"], "ranking": ranked,
                     "pool_size": len(pool)})
    return rows


def run_weighted(cases: list, floor: float) -> list[dict]:
    """Rank all case candidates by weighted score and apply the empty floor."""
    rows = []
    for case in cases:
        scored = sorted(
            ((weighted_score(case["claim"], tx), tx) for tx in case["candidates"]),
            key=lambda pair: (-pair[0], str(pair[1].get("transaction_date") or "")),
        )
        ranked = [tx["transaction_id"] for s, tx in scored if s >= floor]
        rows.append({"case_id": case["case_id"], "ranking": ranked,
                     "scores": {tx["transaction_id"]: round(s, 4) for s, tx in scored}})
    return rows


def run_gbm(cases: list, model, floor: float) -> list[dict]:
    """Rank candidates with a fitted GBM and apply its empty floor."""
    rows = []
    for case in cases:
        feats = [list(features(case["claim"], tx).values()) for tx in case["candidates"]]
        proba = model.predict_proba(feats)[:, 1]
        scored = sorted(
            zip(proba, case["candidates"]),
            key=lambda pair: (-pair[0], str(pair[1].get("transaction_date") or "")),
        )
        ranked = [tx["transaction_id"] for s, tx in scored if s >= floor]
        rows.append({"case_id": case["case_id"], "ranking": ranked})
    return rows


def train_gbm(train_cases: list):
    """Train a histogram gradient-boosting model on customer-disjoint train cases."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    X, y = [], []
    for case in train_cases:
        if case["label_transaction_id"] is None:
            continue
        for tx in case["candidates"]:
            X.append(list(features(case["claim"], tx).values()))
            y.append(1 if tx["transaction_id"] == case["label_transaction_id"] else 0)
    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, random_state=0)
    model.fit(X, y)
    return model


# -------------------------------------------------------------------- métricas

def score(rows: list, cases: list) -> dict:
    """Calculate top-k, no-match, noise-type, and currency metrics."""
    labeled = [c for c in cases if c["label_transaction_id"] is not None]
    unrelated = [c for c in cases if c["label_transaction_id"] is None]
    rows_by_id = {r["case_id"]: r for r in rows}

    def topk(case_list, k):
        hits = 0
        for case in case_list:
            ranking = rows_by_id[case["case_id"]]["ranking"]
            if case["label_transaction_id"] in ranking[:k]:
                hits += 1
        return round(hits / len(case_list), 4) if case_list else None

    result = {
        "n": len(cases),
        "top1": topk(labeled, 1),
        "top3": topk(labeled, 3),
        "empty_on_unrelated": round(statistics.fmean(
            not rows_by_id[c["case_id"]]["ranking"] for c in unrelated), 4) if unrelated else None,
        "false_empty_on_labeled": round(statistics.fmean(
            not rows_by_id[c["case_id"]]["ranking"] for c in labeled), 4),
    }
    # por tipo de ruido y por moneda (solo etiquetados)
    by_noise: dict[str, list] = defaultdict(list)
    by_currency: dict[str, list] = defaultdict(list)
    for case in labeled:
        by_noise[case["noise_type"]].append(case)
        by_currency[case["currency"]].append(case)
    result["top1_by_noise"] = {k: topk(v, 1) for k, v in sorted(by_noise.items())}
    result["top3_by_noise"] = {k: topk(v, 3) for k, v in sorted(by_noise.items())}
    result["top1_by_currency"] = {k: topk(v, 1) for k, v in sorted(by_currency.items())}
    return result


def baseline_views(rows: list, cases: list) -> dict:
    """Return comparison metrics for baseline pools of size one, multiple, or zero."""
    rows_by_id = {r["case_id"]: r for r in rows}
    labeled = [c for c in cases if c["label_transaction_id"] is not None]
    single = [c for c in labeled if len(rows_by_id[c["case_id"]]["ranking"]) == 1]
    multi = [c for c in labeled if len(rows_by_id[c["case_id"]]["ranking"]) >= 2]
    empty = [c for c in labeled if not rows_by_id[c["case_id"]]["ranking"]]

    def hit(case, ranking):
        return case["label_transaction_id"] in ranking[:1]

    return {
        "baseline_pool_1_n": len(single),
        "baseline_pool_1_baseline_top1": round(statistics.fmean(
            hit(c, rows_by_id[c["case_id"]]["ranking"]) for c in single), 4) if single else None,
        "baseline_pool_2plus_n": len(multi),
        "baseline_pool_2plus_baseline_top1": round(statistics.fmean(
            hit(c, rows_by_id[c["case_id"]]["ranking"]) for c in multi), 4) if multi else None,
        "baseline_empty_on_labeled_n": len(empty),
    }


def within_pool_metrics(base_rows: list, cases: list, score_fn) -> dict:
    """Measure reordering only within the pool selected by the baseline.

    A pool of one is unchanged; a pool of multiple candidates measures which
    option is proposed first; an empty pool remains empty.
    """
    base_by_id = {r["case_id"]: r for r in base_rows}
    labeled = [c for c in cases if c["label_transaction_id"] is not None]
    views = {"pool1": [0, 0], "pool2plus": [0, 0]}
    for case in labeled:
        pool_ids = base_by_id[case["case_id"]]["ranking"]
        pool = [tx for tx in case["candidates"] if tx["transaction_id"] in pool_ids]
        key = "pool1" if len(pool) == 1 else "pool2plus" if len(pool) >= 2 else None
        if key is None:
            continue
        ordered = sorted(pool, key=lambda tx: (-score_fn(case["claim"], tx), pool_ids.index(tx["transaction_id"])))
        views[key][1] += 1
        views[key][0] += ordered[0]["transaction_id"] == case["label_transaction_id"]
    return {
        "pool1_n": views["pool1"][1],
        "pool1_top1": round(views["pool1"][0] / views["pool1"][1], 4) if views["pool1"][1] else None,
        "pool2plus_n": views["pool2plus"][1],
        "pool2plus_top1": round(views["pool2plus"][0] / views["pool2plus"][1], 4) if views["pool2plus"][1] else None,
    }


def subset_score(rows: list, cases: list, subset_ids: set) -> float | None:
    """Calculate top-1 accuracy on a selected set of case identifiers."""
    rows_by_id = {r["case_id"]: r for r in rows}
    subset = [c for c in cases if c["case_id"] in subset_ids and c["label_transaction_id"] is not None]
    if not subset:
        return None
    return round(statistics.fmean(
        c["label_transaction_id"] in rows_by_id[c["case_id"]]["ranking"][:1] for c in subset), 4)


def pick_floor_weighted(dev_cases: list) -> float:
    """Choose the highest-scoring weighted floor using train/dev cases only."""
    labeled = [c for c in dev_cases if c["label_transaction_id"] is not None]
    best, best_top1 = FLOOR_GRID[-1], -1.0
    for floor in FLOOR_GRID:
        rows_by_id = {r["case_id"]: r for r in run_weighted(dev_cases, floor)}
        false_empty = sum(1 for c in labeled if not rows_by_id[c["case_id"]]["ranking"])
        top1 = statistics.fmean(
            c["label_transaction_id"] in rows_by_id[c["case_id"]]["ranking"][:1] for c in labeled)
        # el "no encuentra" falso penaliza: exigirlo en cero salvo el piso máximo
        if false_empty > 0 and floor != FLOOR_GRID[-1]:
            continue
        if top1 > best_top1:
            best, best_top1 = floor, top1
    return best


def pick_floor_gbm(model, dev_cases: list) -> float:
    """Choose the GBM empty-pool floor using train/dev cases only."""
    labeled = [c for c in dev_cases if c["label_transaction_id"] is not None]
    best, best_top1 = FLOOR_GRID[-1], -1.0
    for floor in FLOOR_GRID:
        rows_by_id = {r["case_id"]: r for r in run_gbm(dev_cases, model, floor)}
        false_empty = sum(1 for c in labeled if not rows_by_id[c["case_id"]]["ranking"])
        top1 = statistics.fmean(
            c["label_transaction_id"] in rows_by_id[c["case_id"]]["ranking"][:1] for c in labeled)
        if false_empty > 0 and floor != FLOOR_GRID[-1]:
            continue
        if top1 > best_top1:
            best, best_top1 = floor, top1
    return best


# ---------------------------------------------------------------------- main

def main() -> None:
    """Parse CLI options and evaluate baseline, weighted, and GBM rankers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("train", "test"), default="train")
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()

    data = [json.loads(line) for line in
            (Path(__file__).parent / "data" / "dispute_set.jsonl").open(encoding="utf-8")]
    cases = [c for c in data if c["split"] == args.split]
    dev_cases = [c for c in data if c["split"] == "train"]
    print(f"split {args.split}: {len(cases)} casos "
          f"({sum(1 for c in cases if c['label_transaction_id'] is None)} unrelated)")

    results: dict = {"split": args.split}
    failures: dict[str, list] = {}

    # baseline
    base_rows = run_baseline(cases)
    results["baseline"] = score(base_rows, cases)
    results["baseline"].update(baseline_views(base_rows, cases))
    results["baseline"]["top1_by_noise"] = results["baseline"].get("top1_by_noise")

    # vistas del ranker sobre los subsets del baseline (comparación justa)
    base_rows_by_id = {r["case_id"]: r for r in base_rows}
    single_ids = {r["case_id"] for r in base_rows
                  if len(r["ranking"]) == 1
                  and by_case(data, r["case_id"])["label_transaction_id"] is not None}
    multi_ids = {r["case_id"] for r in base_rows
                 if len(r["ranking"]) >= 2
                 and by_case(data, r["case_id"])["label_transaction_id"] is not None}
    empty_ids = {r["case_id"] for r in base_rows
                 if not r["ranking"]
                 and by_case(data, r["case_id"])["label_transaction_id"] is not None}

    # weighted
    floor_w = pick_floor_weighted(dev_cases)
    w_rows = run_weighted(cases, floor_w)
    results["weighted"] = score(w_rows, cases)
    results["weighted"]["floor"] = floor_w
    results["weighted"]["top1_on_baseline_single"] = subset_score(w_rows, cases, single_ids)
    results["weighted"]["top1_on_baseline_multi"] = subset_score(w_rows, cases, multi_ids)
    results["weighted"]["top1_on_baseline_empty"] = subset_score(w_rows, cases, empty_ids)
    results["weighted"]["within_pool"] = within_pool_metrics(base_rows, cases, weighted_score)

    # gbm
    g_rows = None
    try:
        model = train_gbm(dev_cases)
        floor_g = pick_floor_gbm(model, dev_cases)
        g_rows = run_gbm(cases, model, floor_g)
        results["gbm"] = score(g_rows, cases)
        results["gbm"]["floor"] = floor_g
        results["gbm"]["top1_on_baseline_single"] = subset_score(g_rows, cases, single_ids)
        results["gbm"]["top1_on_baseline_multi"] = subset_score(g_rows, cases, multi_ids)
        results["gbm"]["top1_on_baseline_empty"] = subset_score(g_rows, cases, empty_ids)
        results["gbm"]["within_pool"] = within_pool_metrics(
            base_rows, cases, lambda claim, tx: model.predict_proba([list(features(claim, tx).values())])[0][1])
    except ImportError as error:
        results["gbm"] = {"skipped": f"scikit-learn no disponible: {error}"}

    # fallos del mejor ranker vs baseline (para el informe)
    ranker_rows = {"weighted": w_rows, "gbm": g_rows}
    for name, rows in ranker_rows.items():
        if rows is None:
            continue
        rows_by_id = {r["case_id"]: r for r in rows}
        failures[name] = [
            {"case_id": c["case_id"], "claim": c["claim"], "noise_type": c["noise_type"],
             "language": c["language"], "label": c["label_transaction_id"],
             "ranking": rows_by_id[c["case_id"]]["ranking"][:5],
             "baseline_pool": len(base_rows_by_id[c["case_id"]]["ranking"])}
            for c in cases
            if c["label_transaction_id"] is not None
            and c["label_transaction_id"] not in rows_by_id[c["case_id"]]["ranking"][:3]
        ]

    out = REPORTS / f"ranker_results_{args.split}.json"
    REPORTS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, rows in failures.items():
        path = REPORTS / f"ranker_failures_{args.split}_{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    for name in ("baseline", "weighted", "gbm"):
        r = results.get(name) or {}
        if "skipped" in r:
            print(f"{name}: OMITIDO ({r['skipped']})")
            continue
        print(f"\n== {name} ==")
        for key in ("top1", "top3", "empty_on_unrelated", "false_empty_on_labeled", "floor"):
            if key in r:
                print(f"  {key}: {r[key]}")
        print(f"  top1 por ruido: {r.get('top1_by_noise')}")
        print(f"  top1 por moneda: {r.get('top1_by_currency')}")
        if "top1_on_baseline_single" in r:
            print(f"  sobre baseline pool=1 (n={len(single_ids)}): {r['top1_on_baseline_single']}, "
                  f"pool 2+ (n={len(multi_ids)}): {r['top1_on_baseline_multi']}, "
                  f"vacío (n={len(empty_ids)}): {r['top1_on_baseline_empty']}")
        if "within_pool" in r:
            wp = r["within_pool"]
            print(f"  reordenando el pool del baseline: pool=1 (n={wp['pool1_n']}) "
                  f"{wp['pool1_top1']}, pool 2+ (n={wp['pool2plus_n']}) {wp['pool2plus_top1']}")
    print(f"\nresultados: {out}")
    if args.final:
        write_report(results)
        print(f"informe: {REPORTS / 'ranker_eval.md'}")


def by_case(cases: list, case_id: str) -> dict:
    """Return the case record matching ``case_id``."""
    return next(c for c in cases if c["case_id"] == case_id)


def write_report(results: dict) -> None:
    """Write the Markdown report for a completed ranker evaluation."""
    lines = [
        "# Evaluación del componente B: ranking de la transacción disputada",
        "",
        (f"Split: **{results['split']}** de `ml/eval/data/dispute_set.jsonl` "
         "(generado por el equipo; split por cliente, sin columnas de fraude)."),
        "",
        "| candidato | top-1 | top-3 | no-encuentra (unrelated) | vacíos falsos |",
        "|---|---|---|---|---|",
    ]
    for name in ("baseline", "weighted", "gbm"):
        r = results.get(name) or {}
        if "skipped" in r:
            lines.append(f"| {name} | OMITIDO | | | |")
            continue
        lines.append(f"| {name} | {r.get('top1')} | {r.get('top3')} | "
                     f"{r.get('empty_on_unrelated')} | {r.get('false_empty_on_labeled')} |")
    lines.append("")
    for name in ("weighted", "gbm"):
        r = results.get(name) or {}
        if "skipped" in r:
            continue
        lines += [f"## {name}", "",
                  f"- umbral 'no encuentra' elegido en dev: {r.get('floor')}",
                  f"- top-1 por tipo de ruido: {r.get('top1_by_noise')}",
                  f"- top-1 por moneda: {r.get('top1_by_currency')}",
                  f"- sobre los pools del baseline: 1→{r.get('top1_on_baseline_single')}, "  # noqa: ISC004
                  f"2+→{r.get('top1_on_baseline_multi')}, vacío→{r.get('top1_on_baseline_empty')}"]
        if r.get("within_pool"):
            wp = r["within_pool"]
            lines.append(f"- **reordenando el pool del baseline (integración 'ordena, no autoriza')**: "
                         f"pool=1 n={wp['pool1_n']} top-1 {wp['pool1_top1']}; "
                         f"pool 2+ n={wp['pool2plus_n']} top-1 **{wp['pool2plus_top1']}**")
        lines.append("")
    lines += ["## Fallos incluidos", "",
              "`ml/eval/reports/ranker_failures_" + results["split"] + "_<candidato>.jsonl` "
              "reúne los casos fuera del top-3 de cada ranker con el claim, la etiqueta "
              "y el tamaño del pool del baseline."]
    (REPORTS / "ranker_eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
