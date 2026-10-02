from datetime import datetime, timedelta

CUS_A = "CUS-AAAA0001"
CUS_B = "CUS-BBBB0002"


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

    async def create_dispute(self, customer_id, transaction_id, reason_code, summary, evidence):
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
            "created_at": datetime(2026, 9, 30, 12, 0, 0),
            "resolved_at": None,
        }
        self.disputes[case_id] = dispute
        self.events[case_id] = [{"event": "created", "payload": {"reason_code": reason_code}}]
        return dict(dispute)

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
        dispute["status"] = "escalated"
        dispute["evidence"] = {**dispute["evidence"], "handoff": handoff}
        dispute["resolved_at"] = datetime(2026, 9, 30, 12, 5, 0)
        self.events[case_id].append({"event": "escalated", "payload": handoff})
        return dict(dispute)
