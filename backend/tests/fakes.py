from datetime import datetime, timedelta, timezone

from app.db import DEPOSIT_TYPES, CREDIT_TYPES, decode_cursor, encode_cursor, product_kind
from app.passwords import hash_password

CUS_A = "CUS-AAAA0001"
CUS_B = "CUS-BBBB0002"
PASSWORD_A = "Clave-Segura-1"


def _tx(transaction_id: str, customer_id: str, **overrides) -> dict:
    row = {
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "transaction_date": datetime(2026, 6, 10, 12, 0, 0),
        "process_date": datetime(2026, 6, 10).date(),
        "product_id": "PRD-0001",
        "transaction_type": "Purchase",
        "transaction_category": "Retail",
        "amount": "1200.00",
        "currency": "COP",
        "amount_usd": "0.30",
        "channel": "POS",
        "merchant_name": "Tienda Don Pepe",
        "merchant_category": "Groceries",
        "transaction_country": "Colombia",
        "transaction_city": "Bogotá",
        "transaction_status": "Declined",
        "response_code": "51",
    }
    row.update(overrides)
    return row


def _product(product_id, customer_id, product_type, number, currency, balance, credit_limit=None, status="Active"):
    return {
        "product_id": product_id,
        "customer_id": customer_id,
        "product_type": product_type,
        "product_number": number,
        "currency": currency,
        "current_balance": balance,
        "credit_limit": credit_limit,
        "interest_rate": None,
        "opening_date": datetime(2020, 1, 1).date(),
        "product_status": status,
        "days_past_due": None,
        "last_transaction_date": None,
    }


def _public_product(row: dict) -> dict:
    visible = {k: v for k, v in row.items() if k not in ("customer_id", "product_number")}
    visible["product_number_masked"] = "****" + row["product_number"][-4:]
    visible["kind"] = product_kind(row["product_type"])
    return visible


def _with_effective_usd(tx: dict) -> dict:
    row = dict(tx)
    if row["amount_usd"] is None and row["currency"] == "USD":
        row["amount_usd_effective"] = row["amount"]
    else:
        row["amount_usd_effective"] = row["amount_usd"]
    return row


class FakeStore:
    """In-memory stand-in with the same surface as app.db.BankStore."""

    def __init__(self):
        self.customers = {
            CUS_A: {
                "customer_id": CUS_A,
                "document_number": "CC-123",
                "first_name": "Ana",
                "last_name": "García",
                "country": "Colombia",
            },
            CUS_B: {
                "customer_id": CUS_B,
                "document_number": "CPF-456",
                "first_name": "Bruno",
                "last_name": "Souza",
                "country": "Brasil",
            },
        }
        self.transactions = {
            "TXN-A1": _tx("TXN-A1", CUS_A, amount_usd=None, currency="USD", amount="49.90"),
            "TXN-A2": _tx("TXN-A2", CUS_A, transaction_status="Reversed", merchant_name="Farmacia Central", merchant_category="Pharmacy"),
            "TXN-A3": _tx("TXN-A3", CUS_A, transaction_date=datetime(2026, 1, 5, 9, 0, 0), transaction_status="Approved", merchant_name="Librería Norte"),
            "TXN-B1": _tx("TXN-B1", CUS_B),
        }
        self.disputes: dict[str, dict] = {}
        self.events: dict[str, list] = {}
        self._seq = 0
        self.products = {
            "PRD-A-SAV": _product("PRD-A-SAV", CUS_A, "Cuenta Ahorro", "1111222233334444", "COP", "1500000.50"),
            "PRD-A-CC": _product("PRD-A-CC", CUS_A, "Tarjeta Crédito", "5555666677778888", "COP", "320000.00", credit_limit="2000000.00"),
            "PRD-A-OLD": _product("PRD-A-OLD", CUS_A, "Cuenta Corriente", "9999000011112222", "COP", "10.00", status="Closed"),
            "PRD-B-SAV": _product("PRD-B-SAV", CUS_B, "Cuenta Ahorro", "1234123412341234", "BRL", "99.00"),
        }
        self.credentials = {
            "ana.garcia": {
                "customer_id": CUS_A,
                "username": "ana.garcia",
                "password_hash": hash_password(PASSWORD_A),
                "failed_attempts": 0,
                "locked_until": None,
                "demo_label": "Declined over the threshold",
                "demo_hint": "Escalates by amount",
            },
            "bruno.souza": {
                "customer_id": CUS_B,
                "username": "bruno.souza",
                "password_hash": hash_password("otra-clave"),
                "failed_attempts": 0,
                "locked_until": None,
                "demo_label": None,
                "demo_hint": None,
            },
        }

    async def authenticate(self, customer_id: str, document_number: str):
        customer = self.customers.get(customer_id)
        if customer and customer["document_number"] == document_number:
            return customer_id
        return None

    async def get_profile(self, customer_id: str):
        customer = self.customers.get(customer_id)
        if customer is None:
            return None
        return {
            "customer_id": customer["customer_id"],
            "first_name": customer["first_name"],
            "last_name": customer["last_name"],
            "country": customer["country"],
        }

    async def list_transactions(
        self, customer_id, status=None, merchant=None, days=None, limit=20
    ):
        rows = [t for t in self.transactions.values() if t["customer_id"] == customer_id]
        if status:
            rows = [t for t in rows if t["transaction_status"] == status]
        if merchant:
            rows = [t for t in rows if merchant.lower() in t["merchant_name"].lower()]
        if days is not None:
            edge = max(t["transaction_date"] for t in self.transactions.values())
            rows = [t for t in rows if t["transaction_date"] >= edge - timedelta(days=days)]
        rows.sort(key=lambda t: t["transaction_date"], reverse=True)
        return [_with_effective_usd(t) for t in rows[:limit]]

    async def get_transaction(self, customer_id: str, transaction_id: str):
        tx = self.transactions.get(transaction_id)
        if tx is None or tx["customer_id"] != customer_id:
            return None
        return _with_effective_usd(tx)

    async def create_dispute(
        self, customer_id, transaction_id, reason_code, summary, evidence, idempotency_key=None
    ):
        for case in self.disputes.values():
            if case["customer_id"] == customer_id and case["status"] != "closed" and (
                case["transaction_id"] == transaction_id
                or (idempotency_key and case.get("idempotency_key") == idempotency_key)
            ):
                return dict(case), False
        self._seq += 1
        case_id = f"00000000-0000-0000-0000-{self._seq:012d}"
        dispute = {
            "case_id": case_id,
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "reason_code": reason_code,
            "summary": summary,
            "status": "open",
            "evidence": evidence,
            "created_at": datetime(2026, 9, 30, 12, self._seq % 60, 0),
            "resolved_at": None,
            "idempotency_key": idempotency_key,
        }
        self.disputes[case_id] = dispute
        self.events[case_id] = [{"event": "created", "payload": {"reason_code": reason_code}}]
        return dict(dispute), True

    async def get_dispute(self, customer_id: str, case_id: str):
        dispute = self.disputes.get(case_id)
        if dispute is None or dispute["customer_id"] != customer_id:
            return None
        return dict(dispute)

    async def get_dispute_events(self, case_id: str):
        return list(self.events.get(case_id, []))

    async def escalate_dispute(self, customer_id: str, case_id: str, handoff: dict):
        dispute = self.disputes.get(case_id)
        if dispute is None or dispute["customer_id"] != customer_id:
            return None
        if dispute["status"] in ("open", "auto_resolved"):
            dispute["status"] = "escalated"
            dispute["evidence"] = {**dispute["evidence"], "handoff": handoff}
            dispute["resolved_at"] = datetime(2026, 9, 30, 12, 5, 0)
            self.events[case_id].append({"event": "escalated", "payload": handoff})
        return dict(dispute)

    async def resolve_dispute(self, customer_id: str, case_id: str, resolution: dict):
        dispute = self.disputes.get(case_id)
        if dispute is None or dispute["customer_id"] != customer_id:
            return None
        if dispute["status"] == "open":
            dispute["status"] = "auto_resolved"
            dispute["evidence"] = {**dispute["evidence"], "resolution": resolution}
            dispute["resolved_at"] = datetime(2026, 9, 30, 12, 6, 0)
            self.events[case_id].append({"event": "resolved", "payload": resolution})
        return dict(dispute)

    async def list_disputes(self, customer_id, status=None, limit=20):
        rows = [d for d in self.disputes.values() if d["customer_id"] == customer_id and d["status"] != "closed"]
        if status:
            rows = [d for d in rows if d["status"] == status]
        rows.sort(key=lambda d: d["created_at"], reverse=True)
        return [dict(d) for d in rows[:limit]]

    # ---- v1
    async def ping(self):
        return True

    async def list_products(self, customer_id):
        rows = [_public_product(p) for p in self.products.values() if p["customer_id"] == customer_id]
        rows.sort(key=lambda p: (p["product_status"] != "Active", p["product_type"], p["product_id"]))
        return rows

    async def get_product(self, customer_id, product_id):
        row = self.products.get(product_id)
        if row is None or row["customer_id"] != customer_id:
            return None
        return _public_product(row)

    async def list_transactions_page(
        self, customer_id, *, product_id=None, status=None, merchant=None,
        date_from=None, date_to=None, cursor=None, limit=20,
    ):
        rows = [t for t in self.transactions.values() if t["customer_id"] == customer_id]
        if product_id:
            rows = [t for t in rows if t["product_id"] == product_id]
        if status:
            rows = [t for t in rows if t["transaction_status"] == status]
        if merchant:
            rows = [t for t in rows if merchant.lower() in t["merchant_name"].lower()]
        if date_from:
            rows = [t for t in rows if t["transaction_date"].date() >= date_from]
        if date_to:
            rows = [t for t in rows if t["transaction_date"].date() <= date_to]
        rows.sort(key=lambda t: (t["transaction_date"], t["transaction_id"]), reverse=True)
        if cursor:
            moment, last_id = decode_cursor(cursor)
            rows = [t for t in rows if (t["transaction_date"], t["transaction_id"]) < (moment, last_id)]
        page = rows[: limit + 1]
        next_cursor = None
        if len(page) > limit:
            page = page[:limit]
            next_cursor = encode_cursor(page[-1]["transaction_date"], page[-1]["transaction_id"])
        items = []
        for tx in page:
            case = next(
                (d for d in self.disputes.values()
                 if d["customer_id"] == customer_id and d["transaction_id"] == tx["transaction_id"] and d["status"] != "closed"),
                None,
            )
            items.append({**_with_effective_usd(tx), "case_id": case and case["case_id"], "dispute_status": case and case["status"]})
        return items, next_cursor

    async def summary(self, customer_id):
        totals: dict[tuple, dict] = {}
        for p in self.products.values():
            if p["customer_id"] != customer_id or p["product_status"] != "Active":
                continue
            if p["product_type"] in DEPOSIT_TYPES:
                kind = "deposit"
            elif p["product_type"] in CREDIT_TYPES:
                kind = "credit"
            else:
                continue
            row = totals.setdefault((p["currency"], kind), {"currency": p["currency"], "kind": kind, "total": 0, "products": 0})
            row["total"] += float(p["current_balance"])
            row["products"] += 1
        recent, _ = await self.list_transactions_page(customer_id, limit=5)
        counts: dict[str, int] = {}
        for d in self.disputes.values():
            if d["customer_id"] == customer_id and d["status"] != "closed":
                counts[d["status"]] = counts.get(d["status"], 0) + 1
        return {"balances": sorted(totals.values(), key=lambda r: (r["currency"], r["kind"])), "recent_transactions": recent, "disputes": counts}

    async def get_credentials(self, username):
        row = self.credentials.get(username.lower())
        return dict(row) if row else None

    async def record_login_failure(self, customer_id, max_attempts, lock_minutes):
        for row in self.credentials.values():
            if row["customer_id"] == customer_id:
                row["failed_attempts"] += 1
                if row["failed_attempts"] >= max_attempts:
                    row["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)

    async def record_login_success(self, customer_id):
        for row in self.credentials.values():
            if row["customer_id"] == customer_id:
                row["failed_attempts"] = 0
                row["locked_until"] = None

    async def get_customer_names(self, customer_ids):
        return {
            c: {"first_name": self.customers[c]["first_name"], "last_name": self.customers[c]["last_name"]}
            for c in customer_ids if c in self.customers
        }

    async def upsert_credentials(self, customer_id, username, password_hash, demo_label=None, demo_hint=None):
        self.credentials[username.lower()] = {
            "customer_id": customer_id, "username": username, "password_hash": password_hash,
            "failed_attempts": 0, "locked_until": None, "demo_label": demo_label, "demo_hint": demo_hint,
        }

    async def list_demo_accounts(self):
        return [
            {"username": r["username"], "label": r["demo_label"], "hint": r["demo_hint"],
             "first_name": self.customers[r["customer_id"]]["first_name"], "country": self.customers[r["customer_id"]]["country"]}
            for r in self.credentials.values() if r["demo_label"]
        ]
