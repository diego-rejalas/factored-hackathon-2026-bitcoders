"""An evaluation fixture: invented customers and transactions with a known mix, so the policy has enough different
cases to be measured. The three demonstration customers hold only two transactions that can resolve on their own;
a rate over two cases says almost nothing.

Everything here is made up by the team (seeded, so it is reproducible) and is loaded only into the local
development database. The expected outcome of each transaction is derived from the policy table, written down here
independently of the agent's code:

    Declined or Reversed and under USD 500  -> resolves on its own
    Approved or Pending                    -> escalates (money may have moved)
    any amount of USD 500 or more          -> escalates

    python -m eval.fixture    # writes datasets/fixture_eval.sql and datasets/fixture_eval.json
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
THRESHOLD_USD = 500.0
CUTOFF = datetime(2026, 6, 18, 20, 0)

MERCHANTS = [
    ("Supermercado del Sol", "Groceries"), ("Farmacia La Paz", "Pharmacy"), ("Gasolinera Ruta 9", "Fuel"),
    ("Librería Central", "Retail"), ("Café del Parque", "Restaurants"), ("Electro Hogar", "Electronics"),
    ("Viajes Horizonte", "Travel"), ("Tienda Moda Viva", "Retail"), ("Panadería San José", "Groceries"),
    ("Cine Plaza", "Entertainment"), ("Taller Mecánico Rápido", "Services"), ("Mercado Fresco", "Groceries"),
    ("Hotel Los Andes", "Travel"), ("Ferretería Norte", "Retail"), ("Clínica Vida", "Health"),
    ("Streaming Plus", "Entertainment"), ("Óptica Visión", "Health"), ("Juguetería Alegría", "Retail"),
]
CITIES = {"Colombia": ["Bogotá", "Medellín"], "Argentina": ["Córdoba", "Buenos Aires"], "México": ["Monterrey", "Guadalajara"]}
STATUS_WEIGHTS = [("Approved", 0.50), ("Declined", 0.25), ("Reversed", 0.15), ("Pending", 0.10)]


def expected_route(status: str, amount_usd: float) -> str:
    """The policy, restated from the documentation (docs/WORKFLOW.md), not imported from the agent."""
    if status in ("Approved", "Pending"):
        return "escalated"
    if amount_usd >= THRESHOLD_USD:
        return "escalated"
    return "resolved"


def build(seed: int = 20261004, customers: int = 12, per_customer: int = 8):
    rng = random.Random(seed)
    people, transactions = [], []
    countries = list(CITIES)
    for index in range(1, customers + 1):
        country = countries[(index - 1) % 3]
        people.append({
            "customer_id": f"CLI-EVAL{index:08d}",
            "document_number": f"{rng.randint(10_000_000, 99_999_999)}",
            "first_name": f"Cliente{index}",
            "last_name": "Evaluacion",
            "country": country,
            "product_id": f"PRD-EVAL{index:04d}",
        })
    used_amounts: dict[str, set] = {p["customer_id"]: set() for p in people}
    for person in people:
        for number in range(1, per_customer + 1):
            status = rng.choices([s for s, _ in STATUS_WEIGHTS], [w for _, w in STATUS_WEIGHTS])[0]
            # Log-uniform between 8 and 3000 so both sides of the threshold are well represented.
            while True:
                amount = round(10 ** rng.uniform(0.9, 3.5), 2)
                if amount not in used_amounts[person["customer_id"]] and amount <= 3200:
                    used_amounts[person["customer_id"]].add(amount)
                    break
            merchant, category = rng.choice(MERCHANTS)
            when = CUTOFF - timedelta(days=rng.randint(1, 80), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
            transactions.append({
                "transaction_id": f"TXN-EVAL-{person['customer_id'][-2:]}-{number:02d}",
                "customer_id": person["customer_id"], "product_id": person["product_id"], "merchant_name": merchant,
                "merchant_category": category, "amount": amount, "currency": "USD", "status": status,
                "response_code": rng.choice(["51", "14", "54", "05"]) if status in ("Declined", "Reversed", "Pending") else "00",
                "transaction_date": when.strftime("%Y-%m-%d %H:%M:%S"), "country": person["country"],
                "city": rng.choice(CITIES[person["country"]]), "channel": rng.choice(["POS", "Online", "App"]),
                "expected": expected_route(status, amount),
            })
    return people, transactions


def sql(people, transactions) -> str:
    lines = ["-- Evaluation fixture: invented, seeded, local only. Loaded by `python -m eval.fixture --load`.", "",
             "delete from gold.transactions where customer_id like 'CLI-EVAL%';", "delete from gold.products where customer_id like 'CLI-EVAL%';", "delete from gold.customers where customer_id like 'CLI-EVAL%';", ""]
    lines.append("insert into gold.customers values")
    lines.append(",\n".join(f"    ('{p['customer_id']}', '{p['document_number']}', '{p['first_name']}', '{p['last_name']}', '{p['country']}')" for p in people) + ";")
    lines.append("insert into gold.products values")
    lines.append(",\n".join(f"    ('{p['product_id']}', '{p['customer_id']}', 'Tarjeta Débito', '5300{p['product_id'][-4:]}0000', 'USD', 1500.00, null, null, '2021-01-15', 'Active', null, '2026-06-18 12:00:00')" for p in people) + ";")
    lines.append("insert into gold.transactions values")
    rows = []
    for t in transactions:
        rows.append(
            f"    ('{t['transaction_id']}', '{t['transaction_date']}', '{t['transaction_date'][:10]}', '{t['product_id']}', '{t['customer_id']}', "
            f"'Purchase', '{t['merchant_category']}', {t['amount']}, 'USD', {t['amount']}, '{t['channel']}', null, '{t['merchant_name']}', "
            f"'{t['merchant_category']}', '{t['country']}', '{t['city']}', '{t['status']}', '{t['response_code']}')"
        )
    lines.append(",\n".join(rows) + ";")
    return "\n".join(lines) + "\n"


def main():
    import subprocess
    import sys

    people, transactions = build()
    (HERE / "datasets" / "fixture_eval.sql").write_text(sql(people, transactions))
    (HERE / "datasets" / "fixture_eval.json").write_text(json.dumps({"customers": people, "transactions": transactions}, ensure_ascii=False, indent=1) + "\n")
    counts = {}
    for t in transactions:
        counts[(t["status"], t["expected"])] = counts.get((t["status"], t["expected"]), 0) + 1
    print(len(people), "customers,", len(transactions), "transactions", counts)
    if "--load" in sys.argv:
        sql_text = (HERE / "datasets" / "fixture_eval.sql").read_text()
        subprocess.run(
            ["docker", "compose", "-f", str(HERE.parent.parent / "docker-compose.dev.yml"), "exec", "-T", "db", "psql", "-U", "postgres", "-d", "data", "-v", "ON_ERROR_STOP=1"],
            input=sql_text, text=True, check=True,
        )
        print("loaded into the local database")


if __name__ == "__main__":
    main()
