"""Generate the blind intent set: customer messages written by a model that is not the classifier and that never saw
the keyword list, so the baseline is not graded on text written to match it.

The label is the intent each message was asked to express (valid by construction). Two styles per intent and
language: "natural" (as a customer writes) and "no_jargon" (told to avoid the usual banking words, which is where a
keyword baseline is weakest and a model should help). Run once; the committed file is the set.

    OPENROUTER_API_KEY=... python -m eval.generate_intent_set
"""

import asyncio
import json
import os
import re
from pathlib import Path

import httpx

GENERATOR = "openai/gpt-4o-mini"  # not the model that classifies (see OPENROUTER_MODEL)
OUT = Path(__file__).parent / "datasets" / "intent_blind.jsonl"

INTENTS = {
    "dispute": "reports a charge they do not recognise, a duplicated charge, a purchase that was declined but still shows, or a transfer that did not arrive",
    "case_status": "asks how a complaint or case they already opened is going, or asks for its number or status",
    "greeting": "only greets or says thanks, with no request",
    "out_of_scope": "asks for something that is not a dispute: a loan, their balance, a higher card limit, opening or closing an account, changing personal data, an investment",
}
LANGUAGES = {"es": "Spanish (Latin American)", "pt": "Brazilian Portuguese"}
STYLES = {
    "natural": ("20", "Vary the register (formal, casual, rushed), the length (from a few words to three sentences) and include a few typos."),
    "no_jargon": ("10", "Do NOT use the usual banking words for the topic (for example: charge, claim, dispute, loan, balance, limit, case). Say it the way a person who does not know the jargon would."),
}


async def generate(client, key, intent, language, style):
    count, style_rule = STYLES[style]
    prompt = (
        f"Write {count} different chat messages that a customer of a bank sends to the bank's assistant. "
        f"In every message the customer {INTENTS[intent]}. Language: {LANGUAGES[language]}. {style_rule} "
        "Do not number them. Do not mention the intent by name. Return only a JSON array of strings."
    )
    response = await client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": GENERATOR, "temperature": 1.0, "max_tokens": 1800, "messages": [{"role": "user", "content": prompt}]},
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"\[.*\]", text, re.S)
    return [m.strip() for m in json.loads(match.group(0)) if isinstance(m, str) and m.strip()]


async def main():
    key = os.environ["OPENROUTER_API_KEY"]
    rows, seen = [], set()
    async with httpx.AsyncClient(timeout=90) as client:
        jobs = [(i, l, s) for i in INTENTS for l in LANGUAGES for s in STYLES]
        results = await asyncio.gather(*(generate(client, key, i, l, s) for i, l, s in jobs))
    for (intent, language, style), messages in zip(jobs, results):
        for message in messages:
            normalized = " ".join(message.lower().split())
            if normalized in seen:
                continue
            seen.add(normalized)
            rows.append({"id": f"b{len(rows):03d}", "message": message, "label": intent, "language": language, "style": style, "source": "blind-generated", "generator": GENERATOR})
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(len(rows), "messages ->", OUT)


if __name__ == "__main__":
    asyncio.run(main())
