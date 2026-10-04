"""A fresh set of fraud and theft messages, written after the first held-out run showed the fraud rule missing most
phrasings. It is a validation set for the fix: the fix was written from the first run's failures, so measuring it on
those same cases would prove little. Nothing here was shown to the person writing the fix.

    OPENROUTER_API_KEY=... python -m eval.generate_fraud_fresh
"""

import asyncio
import json
import os
import re
from pathlib import Path

import httpx

HERE = Path(__file__).parent
GENERATOR = "openai/gpt-4o-mini"
FIX = json.loads((HERE / "datasets" / "fixture_eval.json").read_text())
CUSTOMERS = [c["customer_id"] for c in FIX["customers"]]
PROMPT = (
    "Write {n} different chat messages that a bank customer sends to the bank's assistant because someone else used "
    "their card or account without permission, or because the card or wallet was lost or stolen, or because they were "
    "scammed. Language: {language}. Vary the situation (online fraud, a cloned card, a lost wallet, a phishing link, "
    "someone who knows their password, an unknown device), the register and the length, and include a few typos. "
    "Do not number them. Return only a JSON array of strings."
)


async def one(client, key, language, n):
    response = await client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": GENERATOR, "temperature": 1.0, "max_tokens": 1500, "messages": [{"role": "user", "content": PROMPT.format(n=n, language=language)}]},
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    return [m.strip() for m in json.JSONDecoder().raw_decode(text[text.index("["):])[0] if isinstance(m, str) and m.strip()]


async def main():
    key = os.environ["OPENROUTER_API_KEY"]
    async with httpx.AsyncClient(timeout=90) as client:
        es, pt = await asyncio.gather(one(client, key, "Latin American Spanish", 24), one(client, key, "Brazilian Portuguese", 24))
    rows = []
    for language, messages in (("es", es), ("pt", pt)):
        for message in messages:
            rows.append({"id": f"f{len(rows):03d}", "category": "fraud", "customer_id": CUSTOMERS[len(rows) % len(CUSTOMERS)], "message": message, "language": language, "expected": {"outcome": "escalated"}})
    (HERE / "datasets" / "fraud_fresh.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(len(rows), "messages")


if __name__ == "__main__":
    asyncio.run(main())
