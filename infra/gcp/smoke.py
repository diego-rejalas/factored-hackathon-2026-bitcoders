"""Smoke for the GCP fallback stack (same mandatory paths as the local E2E).

Usage (after the ETL job has populated gold.*):
  AGENT_URL=https://agent-xxxx.run.app CUSTOMER_ID=CUS-XXXX DOCUMENT_NUMBER=... \
    python smoke.py
Pick a real customer from gold.customers (document_number not null) — see the
SQL in infra/gcp/README.md.
"""

import json
import os
import re
import sys

import httpx

AGENT = os.environ["AGENT_URL"].rstrip("/")
failures: list = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK ' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


with httpx.Client(timeout=30) as client:
    login = client.post(
        f"{AGENT}/session",
        json={
            "customer_id": os.environ["CUSTOMER_ID"],
            "document_number": os.environ["DOCUMENT_NUMBER"],
        },
    )
    check("login 200", login.status_code == 200, login.text[:200])
    token = login.json()["session_token"]

    r = client.post(
        f"{AGENT}/chat",
        json={"session_token": token, "message": "me hicieron un cobro que no reconozco"},
    ).json()
    check("disputa ambigua -> clarify", r.get("outcome") == "clarify", json.dumps(r, ensure_ascii=False)[:200])

    r2 = client.post(
        f"{AGENT}/chat",
        json={"session_token": token, "message": "no fui yo, me robaron"},
    ).json()
    check("fraude -> escalated + handoff", r2.get("outcome") == "escalated" and "handoff" in r2, json.dumps(r2, ensure_ascii=False)[:200])

    check(
        "token basura -> 401",
        client.post(f"{AGENT}/chat", json={"session_token": "x", "message": "hola"}).status_code == 401,
    )

print()
if failures:
    print(f"SMOKE FAILED: {failures}")
    sys.exit(1)
print("SMOKE OK")
