"""Generador del set retenido de disputas (componente B).

Cada caso toma una transacción objetivo y genera una descripción libre con
ruido controlado (monto desviado o aproximado, comercio mal escrito o
ausente, fecha vaga, combinaciones). La etiqueta es el `transaction_id`
original: válida por construcción y rotulada "generado por el equipo".
Sin columnas `is_fraud`/`fraud_score` — el generador las elimina y lo
verifica (requisito del proyecto: nunca son entrada del agente).

Fuentes del pool de transacciones (--source):
- synthetic (default, usada para el set publicado): pool determinista con las
  distribuciones medidas del dataset (estados Approved 92% / Declined 5% /
  Pending 2% / Reversed 1%; merchant_name nulo 76,7%; amount_usd_effective
  nulo ~57% — todo en USD o parte de ARS/COP —; monedas USD/COP/ARS;
  ventana de 90 días anclada al corte 2026-06-18, DISPUTE_WORKFLOW §3).
  Se usa porque este entorno no tiene credenciales de la base; queda
  rotulado como sintético en el informe.
- duckdb RUTA: lee gold.transactions de un archivo DuckDB (ETL local).
- postgres: lee gold.transactions con las variables DBT_PG_* (solo lectura).
En los modos con datos reales las columnas de fraude se descartan al leer.

Split por cliente: los clientes de test no aparecen en train (regla §5.4 de
ML_FINDINGS). Casos "unrelated": la descripción no corresponde a ninguna
transacción del pool (etiqueta None) y miden la tasa de "no encuentra".

Uso:
    python ml/eval/gen_dispute_set.py                          # set publicado
    python ml/eval/gen_dispute_set.py --seed 20261004          # reproducible
    python ml/eval/gen_dispute_set.py --source duckdb:/tmp/latam.duckdb
"""

import argparse
import json
import random
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_CUTOFF = date(2026, 6, 18)
WINDOW_DAYS = 90
PER_NOISE = 60          # 6 tipos de ruido x 60 = 360 casos etiquetados
UNRELATED = 40          # + 40 casos "no está en mi cuenta" = 400
NOISE_TYPES = ("amount_off", "amount_vague", "merchant_misspelled",
               "merchant_missing", "date_vague", "combo")
TRAIN_CUSTOMER_SHARE = 0.55

# Distribuciones medidas (spec/DISPUTE_WORKFLOW.md §3 y spec/DATA_FINDINGS.md).
STATUS_WEIGHTS = [("Approved", 0.92), ("Declined", 0.05), ("Pending", 0.02), ("Reversed", 0.01)]
MERCHANT_NULL_RATE = 0.767
USD_EFFECTIVE_NULL_RATE = 0.57
CURRENCIES = ["USD", "COP", "ARS"]  # sin MXN: ninguna transacción está en MXN (§3)
CURRENCY_WEIGHTS = [0.55, 0.30, 0.15]
CHANNELS = ["POS", "online", "ATM", "transfer"]
TYPE_CATEGORIES = [("Purchase", "groceries"), ("Purchase", "electronics"),
                   ("Purchase", "restaurants"), ("Withdrawal", "cash"),
                   ("Payment", "services"), ("Purchase", "clothing")]

# Objetivo por estado (sobre los 360 casos con etiqueta): disputa real cae más
# en Declined/Reversed, pero Approved y Pending también se disputan (§2).
TARGET_STATUS_WEIGHTS = [("Declined", 140), ("Reversed", 70), ("Approved", 100), ("Pending", 50)]

ES_MERCHANTS = ["Farmacia Vida", "Restaurante El Sabor", "Librería Norte", "Tienda Don Pepe",
                "Mercado Central", "Café Aroma", "Electro Mundo", "Casa Ideas", "Ferretería Sur",
                "Kiosco La Esquina", "Óptima Salud", "Verdulería Don José"]
PT_MERCHANTS = ["Supermercado Bom Preço", "Drogaria Sao Paulo", "Pão de Açúcar Digital",
                "Lojas Americanas Online", "Posto Shell Rodoviaria", "Padaria Pão Quente",
                "Mercadinho do Zé", "Farmácia Popular", "Lanchonete Big Lanche", "Casa & Construção"]
NULL_MERCHANT_TOKENS = [None]


def norm(text: str) -> str:
    """Normalize accents and casing for matching synthetic claim text."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# ------------------------------------------------------------------ pool sintético

def _pick(rng: random.Random, weighted) -> object:
    if isinstance(weighted, list) and len(weighted[0]) == 2 and isinstance(weighted[0][1], (int, float)):
        total = sum(w for _, w in weighted)
        r = rng.random() * total
        for value, w in weighted:
            r -= w
            if r <= 0:
                return value
        return weighted[-1][0]
    return rng.choice(weighted)


def amount_for_currency(currency: str, rng: random.Random) -> float:
    """Sample a plausible local transaction amount for one currency."""
    if currency == "USD":
        return round(rng.uniform(3, 900), 2)
    if currency == "COP":
        return float(rng.randrange(5_000, 900_000, 100))
    return float(rng.randrange(500, 180_000, 50))  # ARS


def synthetic_pool(rng: random.Random, customers: int = 800) -> list[dict]:
    """Pool determinista con las distribuciones documentadas del dataset."""
    cutoff = datetime.combine(DATA_CUTOFF, datetime.min.time())
    rows = []
    tx_n = 0
    for c in range(customers):
        customer_id = f"CUS-EVAL-{c:04d}"
        n_tx = rng.randint(6, 18)
        pool_dates = sorted(
            cutoff - timedelta(days=rng.randint(0, WINDOW_DAYS - 1),
                               hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
            for _ in range(n_tx)
        )
        for d in pool_dates:
            tx_n += 1
            currency = _pick(rng, list(zip(CURRENCIES, CURRENCY_WEIGHTS)))
            local = amount_for_currency(currency, rng)
            merchant = None if rng.random() < MERCHANT_NULL_RATE else rng.choice(ES_MERCHANTS + PT_MERCHANTS)
            local_in_usd = currency == "USD" or (currency in ("COP", "ARS") and rng.random() < 0.35)
            effective = round(local / (1.0 if currency == "USD" else {"COP": 4000.0, "ARS": 1200.0}[currency]), 2) \
                if local_in_usd else None
            rows.append({
                "transaction_id": f"TXN-S{tx_n:06d}",
                "customer_id": customer_id,
                "transaction_date": d.replace(microsecond=0, tzinfo=None).isoformat(),
                "merchant_name": merchant,
                "transaction_status": _pick(rng, STATUS_WEIGHTS),
                "amount": local,
                "currency": currency,
                "amount_usd_effective": effective,
                "channel": rng.choice(CHANNELS),
                "transaction_type": rng.choice(TYPE_CATEGORIES)[0],
            })
    return rows


def pool_from_duckdb(path: str, rng: random.Random) -> list[dict]:
    """Read a sample of gold transactions from a local DuckDB database."""
    import duckdb

    con = duckdb.connect(path, read_only=True)
    try:
        cols = [r[0] for r in con.execute("describe gold.transactions").fetchall()]
        keep = [c for c in ("transaction_id", "customer_id", "transaction_date", "merchant_name",
                            "transaction_status", "amount", "currency", "amount_usd_effective",
                            "channel", "transaction_type") if c in cols]
        rows = con.execute(
            f"SELECT {', '.join(keep)} FROM gold.transactions USING SAMPLE 40000 ROWS"
        ).fetchall()
    finally:
        con.close()
    return [dict(zip(keep, r)) for r in rows]


def pool_from_postgres(rng: random.Random) -> list[dict]:
    """Read a read-only sample of gold transactions from configured Postgres."""
    import os

    import pandas as pd
    import psycopg2

    with open(os.environ["ENVF"], encoding="utf-8") as env_file:
        env = dict(
            line.strip().removeprefix("export ").split("=", 1)
            for line in env_file if "=" in line
        )
    con = psycopg2.connect(host=env["DBT_PG_HOST"], port=env["DBT_PG_PORT"],
                           dbname=env["DBT_PG_DATABASE"], user=env["DBT_PG_USER"],
                           password=env["DBT_PG_PASSWORD"])
    con.set_session(readonly=True, autocommit=True)
    cols = ("transaction_id", "customer_id", "transaction_date", "merchant_name",
            "transaction_status", "amount", "currency", "amount_usd_effective",
            "channel", "transaction_type")
    df = pd.read_sql(
        f"SELECT {', '.join(cols)} FROM gold.transactions TABLESAMPLE SYSTEM (1)", con)
    con.close()
    return df.to_dict("records")


def strip_fraud(rows: list[dict]) -> list[dict]:
    """Remove fraud-label columns from every transaction row in place."""
    banned = ("is_fraud", "fraud_score")
    for row in rows:
        for key in banned:
            row.pop(key, None)
    return rows


# ------------------------------------------------------------------ ruido de texto

def typo(word: str, rng: random.Random) -> str:
    """Apply a seeded transposition, vowel substitution, or deletion."""
    if len(word) < 4:
        return word
    i = rng.randrange(1, len(word) - 2)
    kind = rng.random()
    if kind < 0.4:  # transposición
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if kind < 0.7:  # vocal cambiada
        vowels = "aeiou"
        pos = next((j for j in range(i, len(word)) if word[j] in vowels), i)
        return word[:pos] + rng.choice(vowels) + word[pos + 1:]
    return word[:i] + word[i + 1]  # letra omitida


def format_amount(value: float, currency: str, rng: random.Random) -> str:
    """Format a currency amount in US or Latin American numeric style."""
    text = f"{value:,.2f}" if currency == "USD" else f"{value:,.0f}"
    if rng.random() < 0.6:  # estilo latinoamericano: coma decimal
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return text


def date_phrase(days_ago: int, language: str, rng: random.Random) -> str:
    """Generate a vague Spanish or Portuguese phrase for a relative date."""
    if days_ago <= 1:
        return {"es": "ayer", "pt": "ontem"}[language]
    if days_ago <= 3 and rng.random() < 0.5:
        return {"es": "anteayer", "pt": "anteontem"}[language]
    if days_ago <= 7:
        return {"es": "la semana pasada", "pt": "semana passada"}[language]
    if days_ago >= 21 and rng.random() < 0.4:
        return {"es": "a principios de mes", "pt": "no começo do mês"}[language]
    n = max(2, days_ago + rng.randint(-2, 2))
    return {"es": f"hace {n} días", "pt": f"há {n} dias"}[language]


def build_claim(target: dict, language: str, noise: str | None, rng: random.Random) -> tuple[str, str]:
    """Generate a localized claim and the noise type actually used.

    The realized noise can change when the target has no merchant (76.7% of
    the documented population).
    """
    merchant = target.get("merchant_name")
    amount = float(target["amount"])
    currency = target["currency"]
    days_ago = (DATA_CUTOFF - date.fromisoformat(target["transaction_date"][:10])).days
    clamp = lambda v: max(1.0, round(v, 2))

    def amount_text(lo=1.0, hi=1.0):
        return format_amount(clamp(amount * rng.uniform(lo, hi)), currency, rng)

    def vague_amount_text():
        step = 10 ** max(0, len(str(int(amount))) - 2)
        base = round(amount / step) * step
        text = format_amount(base, currency, rng)
        if rng.random() < 0.5:
            return rng.choice(["unos ", "alrededor de ", "más o menos ", "uns ", "cerca de "]) + text
        return text

    merch_text: str | None = None
    amt_text: str | None = None
    dt_text: str | None = None
    chosen = noise or "unrelated"

    if noise == "amount_off":
        amt_text = amount_text(0.82, 0.90) if rng.random() < 0.5 else amount_text(1.10, 1.20)
    elif noise == "amount_vague":
        amt_text = vague_amount_text()
    elif noise == "merchant_misspelled":
        if merchant:
            merch_text = typo(merchant, rng)
        else:  # sin comercio, el ruido cae al monto y el tipo real cambia
            amt_text = amount_text(0.85, 0.92)
            chosen = "amount_off"
    elif noise == "merchant_missing":
        amt_text = vague_amount_text() if rng.random() < 0.5 else amount_text(0.85, 1.15)
    elif noise == "date_vague":
        dt_text = date_phrase(days_ago, language, rng)
        if rng.random() < 0.7:
            amt_text = amount_text(0.82, 0.90) if rng.random() < 0.5 else amount_text(1.10, 1.20)
    elif noise == "combo":
        first, second = rng.sample(["off", "vague", "date", "typo"], 2)
        if "off" in (first, second):
            amt_text = amount_text(0.82, 0.90) if rng.random() < 0.5 else amount_text(1.10, 1.20)
        elif "vague" in (first, second):
            amt_text = vague_amount_text()
        if "date" in (first, second):
            dt_text = date_phrase(days_ago, language, rng)
        if "typo" in (first, second):
            merch_text = typo(merchant, rng) if merchant else None
            if not merch_text and not amt_text:
                amt_text = amount_text(0.85, 0.92)
    elif chosen == "unrelated":
        # describe algo que no está en el pool: otro comercio o un monto imposible
        others = [m for m in ES_MERCHANTS + PT_MERCHANTS if norm(m) != norm(merchant or "")]
        if rng.random() < 0.6:
            merch_text = rng.choice(others)
            amt_text = amount_text(0.7, 1.4)
        else:
            amt_text = format_amount(clamp(amount * rng.uniform(4, 9)), currency, rng)
        dt_text = date_phrase(min(days_ago + 7, WINDOW_DAYS - 1), language, rng)
    else:  # sin ruido pedido (no ocurre en el set publicado)
        amt_text = amount_text()

    if language == "es":
        claim = rng.choice([
            "Me hicieron un cobro que no reconozco",
            "No reconozco este cargo",
            "Me aparece un cargo que no autoricé",
            "Tengo un cobro que no hice",
        ])
        if merch_text:
            claim += f" de {merch_text}"
        if amt_text:
            claim += f" de {amt_text}"
        if dt_text:
            claim += f", {dt_text}"
    else:
        claim = rng.choice([
            "Reconheço uma cobrança que não fiz",
            "Apareceu um lançamento que não autorizei",
            "Tem uma cobrança que não reconheço",
            "Cobraram algo que não foi eu",
        ])
        if merch_text:
            claim += f" da {merch_text}"
        if amt_text:
            claim += f" de {amt_text}"
        if dt_text:
            claim += f", {dt_text}"
    return claim, chosen


# -------------------------------------------------------------------------- main

def main() -> None:
    """Generate the customer-disjoint dispute set and print its data summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--source", default="synthetic")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent / "data" / "dispute_set.jsonl")
    args = parser.parse_args()
    rng = random.Random(args.seed)

    if args.source == "synthetic":
        pool = synthetic_pool(rng)
        provenance = "synthetic (distribuciones documentadas de DATA_FINDINGS/DISPUTE_WORKFLOW)"
    elif args.source.startswith("duckdb:"):
        pool = pool_from_duckdb(args.source.split(":", 1)[1], rng)
        provenance = f"gold.transactions via duckdb ({args.source})"
    elif args.source == "postgres":
        pool = pool_from_postgres(rng)
        provenance = "gold.transactions via postgres (DBT_PG_*)"
    else:
        raise SystemExit(f"fuente desconocida: {args.source}")
    pool = strip_fraud(pool)
    assert all("is_fraud" not in row and "fraud_score" not in row for row in pool)

    by_customer: dict[str, list[dict]] = {}
    for row in pool:
        by_customer.setdefault(row["customer_id"], []).append(row)
    customers = sorted(by_customer)
    rng.shuffle(customers)
    train_cut = int(len(customers) * TRAIN_CUSTOMER_SHARE)
    split_of = {c: ("train" if i < train_cut else "test") for i, c in enumerate(customers)}

    def in_window(tx: dict) -> bool:
        day = date.fromisoformat(str(tx["transaction_date"])[:10])
        return (DATA_CUTOFF - day).days < WINDOW_DAYS

    eligible = {c: [t for t in txs if in_window(t) and t.get("amount") is not None]
                for c, txs in by_customer.items()}
    eligible = {c: txs for c, txs in eligible.items() if len(txs) >= 3}

    noise_pool = [n for n in NOISE_TYPES for _ in range(PER_NOISE)]
    rng.shuffle(noise_pool)
    languages = (["es", "pt"] * (sum(n for _, n in TARGET_STATUS_WEIGHTS) // 2 + 1))
    lang_cycle = iter(languages)

    cases: list[dict] = []
    used_targets: set[str] = set()

    def take_target(status: str, require_merchant: bool = False) -> tuple[str, dict] | None:
        """Select an unused transaction of the requested status.

        Multiple distinct targets may come from one customer. Misspelled-
        merchant cases require a non-null merchant value.
        """
        def ok(t):
            return (t["transaction_status"] == status
                    and t["transaction_id"] not in used_targets
                    and (t.get("merchant_name") or not require_merchant))

        options = [c for c, txs in eligible.items() if any(ok(t) for t in txs)]
        if not options:
            return None
        customer = rng.choice(options)
        target = rng.choice([t for t in eligible[customer] if ok(t)])
        used_targets.add(target["transaction_id"])
        return customer, target

    deferred: list[tuple[str, str]] = []  # (status, noise) sin cliente disponible
    # --- casos con etiqueta: status-major, un caso por combinación ---
    for status, quota in TARGET_STATUS_WEIGHTS:
        for _ in range(quota):
            if not noise_pool:
                break
            noise = noise_pool.pop()
            language = next(lang_cycle)
            slot = take_target(status, require_merchant=(noise == "merchant_misspelled"))
            if slot is None:
                deferred.append((status, noise))
                continue
            customer, target = slot
            claim, real_noise = build_claim(target, language, noise, rng)
            cases.append({
                "case_id": None, "split": split_of[customer], "language": language,
                "noise_type": real_noise, "target_status": status,
                "currency": target["currency"], "claim": claim,
                "label_transaction_id": target["transaction_id"],
                "customer_id": customer,
            })
    if deferred:
        print(f"aviso: {len(deferred)} combinaciones status+ruido sin objetivo disponible "
              f"(agranda el pool con --source real o más clientes)")

    # --- casos unrelated: etiqueta None (el "no encuentra" correcto) ---
    unrelated_done = 0
    attempts = 0
    while unrelated_done < UNRELATED and attempts < UNRELATED * 50:
        attempts += 1
        customer = rng.choice(customers)
        txs = eligible.get(customer) or []
        if not txs:
            continue
        language = rng.choice(["es", "pt"])
        claim, real_noise = build_claim(txs[0], language, None, rng)
        if real_noise != "unrelated":
            continue
        cases.append({
            "case_id": None, "split": split_of[customer], "language": language,
            "noise_type": "unrelated", "target_status": None,
            "currency": txs[0]["currency"], "claim": claim,
            "label_transaction_id": None,
            "customer_id": customer,
        })
        unrelated_done += 1

    rng.shuffle(cases)
    fields = ("case_id", "split", "language", "noise_type", "target_status", "currency",
              "claim", "label_transaction_id", "candidates")
    with args.output.open("w", encoding="utf-8") as fh:
        for i, case in enumerate(cases, 1):
            case["case_id"] = f"DSP-{i:04d}"
            candidates = sorted(
                eligible[case["customer_id"]],
                key=lambda t: str(t.get("transaction_date") or ""), reverse=True,
            )
            case["candidates"] = [
                {k: t.get(k) for k in ("transaction_id", "transaction_date", "merchant_name",
                                       "transaction_status", "amount", "currency",
                                       "amount_usd_effective", "channel", "transaction_type")}
                for t in candidates
            ]
            customer_id = case["customer_id"]  # se excluye del JSON (fields no lo incluye)
            assert customer_id
            # barrera anti-fuga: sin columnas de fraude en el set publicado
            for candidate in case["candidates"]:
                assert "is_fraud" not in candidate and "fraud_score" not in candidate
            if case["label_transaction_id"] is not None:
                assert case["label_transaction_id"] in {c["transaction_id"] for c in case["candidates"]}
            fh.write(json.dumps({k: case[k] for k in fields}, ensure_ascii=False) + "\n")

    counts = Counter((c["split"], c["noise_type"]) for c in cases)
    print(f"escrito {args.output} ({len(cases)} casos, semilla {args.seed}, fuente: {provenance})")
    for split in ("train", "test"):
        row = " ".join(f"{nt}:{counts[(split, nt)]}" for nt in ("amount_off", "amount_vague",
                       "merchant_misspelled", "merchant_missing", "date_vague", "combo", "unrelated"))
        print(f"  {split:5s} {row}")
    status_counts = Counter(c["target_status"] for c in cases if c["target_status"])
    print("estados del objetivo:", dict(status_counts))
    print("idiomas:", dict(Counter(c["language"] for c in cases)))
    train_customers = {c["customer_id"] for c in cases if c["split"] == "train"}
    test_customers = {c["customer_id"] for c in cases if c["split"] == "test"}
    print(f"clientes train {len(train_customers)}, test {len(test_customers)}, "
          f"intersección {len(train_customers & test_customers)} (debe ser 0)")
    pool_sizes = [len(c["candidates"]) for c in cases]
    print(f"tamaño del pool de candidatas: min {min(pool_sizes)}, mediana {sorted(pool_sizes)[len(pool_sizes)//2]}, max {max(pool_sizes)}")


if __name__ == "__main__":
    main()
