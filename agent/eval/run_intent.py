"""Evaluate the intent classifier: the keyword baseline against the model, on the held-out sets.

The sets were written before this ran and nothing was tuned afterwards: the baseline's keywords and the model's
prompt are the ones in app/. Per-case predictions are committed next to the summary so every number can be
recomputed.

    OPENROUTER_API_KEY=... OPENROUTER_MODEL=anthropic/claude-haiku-4.5 python -m eval.run_intent
"""

import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path

from app.intents import INTENTS, baseline_classify, classify_detailed
from app.llm import LLM
from eval import stats

HERE = Path(__file__).parent
SETS = {"blind": HERE / "datasets" / "intent_blind.jsonl", "adversarial": HERE / "datasets" / "intent_adversarial.jsonl"}
LABELS = list(INTENTS)


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def classify_with_model(llm: LLM, message: str) -> tuple[dict | None, float]:
    """The production path: the structured classification with confidence, not the older single-label prompt."""
    start = time.monotonic()
    detail = await llm.classify_detailed(message)
    return detail, (time.monotonic() - start) * 1000


async def evaluate(rows, llm, concurrency=8):
    gate = asyncio.Semaphore(concurrency)

    async def one(row):
        async with gate:
            detail, latency = await classify_with_model(llm, row["message"])
        baseline = baseline_classify(row["message"])
        label = detail["intent"] if detail else None
        # What the agent really does: the model's label when it gives a valid one, otherwise the keywords.
        system = label if label in INTENTS else baseline
        confidence = detail["confidence"] if detail else None
        return {**row, "baseline": baseline, "model": label, "system": system, "confidence": confidence,
                "model_latency_ms": round(latency, 1)}

    return await asyncio.gather(*(one(r) for r in rows))


def summarize(results, llm_usage):
    def acc(key, subset):
        return stats.rate(sum(1 for r in subset if r[key] == r["label"]), len(subset))

    def group(field):
        buckets = defaultdict(list)
        for r in results:
            buckets[r.get(field) or "-"].append(r)
        return {name: {"n": len(rs), "baseline": acc("baseline", rs), "system": acc("system", rs)} for name, rs in sorted(buckets.items())}

    only_baseline = sum(1 for r in results if r["baseline"] == r["label"] and r["system"] != r["label"])
    only_system = sum(1 for r in results if r["system"] == r["label"] and r["baseline"] != r["label"])
    latencies = [r["model_latency_ms"] for r in results]
    calls = max(llm_usage["calls"], 1)
    return {
        "n": len(results),
        "accuracy": {"baseline": acc("baseline", results), "system": acc("system", results)},
        "macro_f1": {
            "baseline": stats.macro_f1([(r["label"], r["baseline"]) for r in results], LABELS),
            "system": stats.macro_f1([(r["label"], r["system"]) for r in results], LABELS),
        },
        "by_language": group("language"),
        "by_style_or_kind": group("style") if any("style" in r for r in results) else group("kind"),
        "by_label": {label: {"n": sum(1 for r in results if r["label"] == label), "baseline": acc("baseline", [r for r in results if r["label"] == label]), "system": acc("system", [r for r in results if r["label"] == label])} for label in LABELS},
        "confusion": {
            "baseline": stats.confusion([(r["label"], r["baseline"]) for r in results], LABELS),
            "system": stats.confusion([(r["label"], r["system"]) for r in results], LABELS),
        },
        "paired": {"only_baseline_right": only_baseline, "only_system_right": only_system, "mcnemar_exact_p": round(stats.mcnemar_exact(only_baseline, only_system), 6)},
        "model_returned_no_valid_label": sum(1 for r in results if r["model"] is None),
        # Confidence below this sends the case to a person (INTENT_MIN_CONFIDENCE, default 0.5): how often, and how right the rest is.
        "abstains_below_0.5": stats.rate(sum(1 for r in results if r["confidence"] is not None and r["confidence"] < 0.5), len(results)),
        "accuracy_when_it_does_not_abstain": acc("system", [r for r in results if r["confidence"] is None or r["confidence"] >= 0.5]),
        "model_latency_ms": {"p50": stats.percentile(latencies, 0.5), "p95": stats.percentile(latencies, 0.95)},
        "tokens": {"prompt": llm_usage["prompt_tokens"], "completion": llm_usage["completion_tokens"]},
        "cost_usd_total": round(llm_usage["cost"], 6) if llm_usage["cost_reported_calls"] else None,
        "cost_usd_per_message": round(llm_usage["cost"] / calls, 6) if llm_usage["cost_reported_calls"] else None,
    }


async def main():
    llm = LLM()
    assert llm.enabled, "needs OPENROUTER_API_KEY"
    report = {"model": llm.models[0], "sets": {}}
    for name, path in SETS.items():
        before = dict(llm.usage)
        rows = load(path)
        results = await evaluate(rows, llm)
        used = {k: llm.usage[k] - before[k] for k in llm.usage}
        report["sets"][name] = summarize(results, used)
        (HERE / "results" / f"intent_{name}_cases.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results))
        print(name, "n =", len(results), "baseline", report["sets"][name]["accuracy"]["baseline"]["value"], "system", report["sets"][name]["accuracy"]["system"]["value"])
    (HERE / "results" / "intent_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
