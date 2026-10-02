import os

from datetime import datetime

CUS_A = "CUS-AAAA0001"
CUS_B = "CUS-BBBB0002"
TEST_SECRET = os.environ.get("SESSION_JWT_SECRET", "test-secret")


def _tx(txid, customer_id, merchant, status, amount, effective=None, date="2026-06-10T12:00:00"):
    return {
        "transaction_id": txid,
        "customer_id": customer_id,
        "transaction_date": date,
        "merchant_name": merchant,
        "transaction_status": status,
        "amount": amount,
        "currency": "USD",
        "amount_usd_effective": effective if effective is not None else amount,
        "transaction_type": "Purchase",
    }


def default_transactions():
    return [
        _tx("TXN-1", CUS_A, "Tienda Don Pepe", "Declined", 45.50),
        _tx("TXN-4", CUS_A, "Tienda Don Pepe", "Declined", 19.99, date="2026-06-05T18:00:00"),
        _tx("TXN-2", CUS_A, "Farmacia Central", "Declined", 120.00, date="2026-06-09T10:00:00"),
        _tx("TXN-3", CUS_A, "Librería Norte", "Reversed", 30.00, date="2026-06-08T09:00:00"),
        _tx("TXN-B1", CUS_B, "Mega Mercado", "Declined", 99.00),
    ]


class FakeBankTools:
    """Same surface as app.tools.BankTools, in memory. Tokens are
    'token-<customer_id>' so ownership rules stay observable."""

    def __init__(self, transactions=None, ambiguous_merchant=None):
        self.transactions = transactions if transactions is not None else default_transactions()
        self.disputes: dict = {}
        self.calls: list = []
        self._seq = 0

    def calls_of(self, method):
        return [c for c in self.calls if c[0] == method]

    async def login(self, customer_id: str, document_number: str) -> dict:
        self.calls.append(("login", customer_id))
        if document_number == "bad":
            from app.tools import ToolError

            raise ToolError(401, "Invalid customer_id or document_number")
        return {"session_token": f"token-{customer_id}", "token_type": "bearer"}

    def _own(self, token):
        from app.tools import ToolError

        if token and token.count(".") == 2:
            import jwt

            try:
                payload = jwt.decode(
                    token, TEST_SECRET, algorithms=["HS256"], issuer="backend-sandbox"
                )
            except jwt.PyJWTError:
                raise ToolError(401, "Invalid or expired session token")
            return payload["sub"]
        if not token or not token.startswith("token-"):
            raise ToolError(401, "Invalid or expired session token")
        return token.removeprefix("token-")

    async def list_transactions(self, token, status=None, merchant=None, days=None, limit=50):
        customer = self._own(token)
        self.calls.append(("list_transactions", {"status": status, "days": days}))
        rows = [t for t in self.transactions if t["customer_id"] == customer]
        if status:
            rows = [t for t in rows if t["transaction_status"] == status]
        return rows[:limit]

    async def get_transaction(self, token, transaction_id):
        customer = self._own(token)
        self.calls.append(("get_transaction", transaction_id))
        for tx in self.transactions:
            if tx["transaction_id"] == transaction_id:
                if tx["customer_id"] != customer:
                    from app.tools import ToolError

                    raise ToolError(404, "Transaction not found for this customer")
                return tx
        from app.tools import ToolError

        raise ToolError(404, "Transaction not found for this customer")

    async def create_dispute(self, token, transaction_id, reason_code, summary):
        customer = self._own(token)
        self.calls.append(("create_dispute", {"transaction_id": transaction_id, "reason_code": reason_code}))
        for tx in self.transactions:
            if tx["transaction_id"] == transaction_id:
                if tx["customer_id"] != customer:
                    from app.tools import ToolError

                    raise ToolError(404, "Transaction not found for this customer")
                self._seq += 1
                case_id = f"00000000-0000-0000-0000-{self._seq:012d}"
                case = {
                    "case_id": case_id,
                    "customer_id": customer,
                    "transaction_id": transaction_id,
                    "reason_code": reason_code,
                    "summary": summary,
                    "status": "open",
                    "evidence": {"transaction": tx},
                }
                self.disputes[case_id] = case
                return case
        from app.tools import ToolError

        raise ToolError(404, "Transaction not found for this customer")

    async def get_dispute(self, token, case_id):
        customer = self._own(token)
        self.calls.append(("get_dispute", case_id))
        case = self.disputes.get(case_id)
        if case is None or case["customer_id"] != customer:
            from app.tools import ToolError

            raise ToolError(404, "Dispute not found")
        return dict(case)

    async def resolve_dispute(self, token, case_id, resolution):
        customer = self._own(token)
        self.calls.append(("resolve_dispute", {"case_id": case_id}))
        case = self.disputes.get(case_id)
        if case is None or case["customer_id"] != customer:
            from app.tools import ToolError

            raise ToolError(404, "Dispute not found")
        if case["status"] == "open":
            case["status"] = "auto_resolved"
            case["evidence"] = {**case["evidence"], "resolution": resolution}
        return dict(case)

    async def escalate_dispute(self, token, case_id, handoff):
        customer = self._own(token)
        self.calls.append(("escalate_dispute", {"case_id": case_id}))
        case = self.disputes.get(case_id)
        if case is None or case["customer_id"] != customer:
            from app.tools import ToolError

            raise ToolError(404, "Dispute not found")
        case["status"] = "escalated"
        case["evidence"] = {**case["evidence"], "handoff": handoff}
        return dict(case)
