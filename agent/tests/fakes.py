import os

import jwt
from app.tracing import NullTracer
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

    async def ready(self) -> bool:
        return True

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
        tx = None
        if transaction_id is not None:
            for candidate in self.transactions:
                if candidate["transaction_id"] == transaction_id:
                    if candidate["customer_id"] != customer:
                        from app.tools import ToolError

                        raise ToolError(404, "Transaction not found for this customer")
                    tx = candidate
                    break
            if tx is None:
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
            "evidence": {"transaction": tx} if tx else {},
        }
        self.disputes[case_id] = case
        return case

    async def get_dispute(self, token, case_id):
        customer = self._own(token)
        self.calls.append(("get_dispute", case_id))
        case = self.disputes.get(case_id)
        if case is None or case["customer_id"] != customer:
            from app.tools import ToolError

            raise ToolError(404, "Dispute not found")
        return dict(case)

    async def list_disputes(self, token):
        customer = self._own(token)
        self.calls.append(("list_disputes", customer))
        rows = sorted(
            (d for d in self.disputes.values() if d["customer_id"] == customer),
            key=lambda d: d["case_id"],
            reverse=True,
        )
        return [
            {
                "case_id": d["case_id"],
                "transaction_id": d["transaction_id"],
                "reason_code": d["reason_code"],
                "status": d["status"],
            }
            for d in rows
        ]

    async def resolve_dispute(self, token, case_id, resolution):
        customer = self._own(token)
        self.calls.append(("resolve_dispute", {"case_id": case_id, "resolution": resolution}))
        case = self.disputes.get(case_id)
        if case is None or case["customer_id"] != customer:
            from app.tools import ToolError

            raise ToolError(404, "Dispute not found")
        if case["status"] == "auto_resolved":
            return dict(case)
        if case["status"] != "open":
            from app.tools import ToolError

            raise ToolError(409, f"Case in status '{case['status']}' cannot be auto-resolved")
        case["status"] = "auto_resolved"
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

    # --- admin console surface -----------------------------------------------------------------

    async def admin_login(self, username: str, password: str) -> dict:
        self.calls.append(("admin_login", username))
        if password != "demo-password":
            from app.tools import ToolError

            raise ToolError(401, "Invalid admin username or password")
        import time

        now = int(time.time())
        token = jwt.encode(
            {"sub": username, "role": "admin", "iat": now, "exp": now + 3600, "iss": "backend-sandbox"},
            TEST_SECRET,
            algorithm="HS256",
        )
        return {"session_token": token, "token_type": "bearer"}

    async def admin_list_disputes(
        self, token, status=None, customer_id=None, limit=50, offset=0
    ) -> dict:
        self.calls.append(("admin_list_disputes", {"status": status, "customer_id": customer_id}))
        rows = [
            {
                "case_id": d["case_id"],
                "customer_id": d["customer_id"],
                "status": d["status"],
                "handoff_reason": (d.get("evidence") or {}).get("handoff", {}).get("reason"),
            }
            for d in self.disputes.values()
        ]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if customer_id:
            rows = [r for r in rows if r["customer_id"] == customer_id]
        return {"items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    async def admin_get_dispute(self, token, case_id) -> dict:
        self.calls.append(("admin_get_dispute", case_id))
        case = self.disputes.get(case_id)
        if case is None:
            from app.tools import ToolError

            raise ToolError(404, "Dispute not found")
        detail = dict(case)
        detail["handoff"] = (case.get("evidence") or {}).get("handoff")
        detail["conversation_id"] = (detail["handoff"] or {}).get("conversation_id")
        detail["events"] = [{"event": "created"}, {"event": "escalated"}]
        return detail

    async def admin_transition(self, token, case_id, action, note="", resolution=None) -> dict:
        self.calls.append(("admin_transition", {"case_id": case_id, "action": action}))
        case = self.disputes.get(case_id)
        if case is None:
            from app.tools import ToolError

            raise ToolError(404, "Dispute not found")
        allowed = {"claim": ("escalated", "open"), "close": ("in_progress",)}
        if case["status"] not in allowed[action]:
            from app.tools import ToolError

            raise ToolError(409, f"Cannot {action} a case in status '{case['status']}'")
        case["status"] = "in_progress" if action == "claim" else "closed"
        return dict(case)

    async def admin_metrics(self, token, window_hours=None) -> dict:
        self.calls.append(("admin_metrics", {"window_hours": window_hours}))
        return {
            "total_cases": len(self.disputes),
            "by_status": {},
            "safe_automated_resolution": {"resolved": 0, "attempted": len(self.disputes), "rate_percent": None},
        }

    async def get_meta_data(self, token) -> dict:
        self.calls.append(("get_meta_data", None))
        return {"gold": {"customers": 10}, "last_etl_run": {"status": "success"}}

    async def get_demo_scenarios(self) -> dict:
        self.calls.append(("get_demo_scenarios", None))
        return {
            "scenarios": [
                {
                    "scenario": "auto_resolved",
                    "customer_id": CUS_A,
                    "document_number": "CC-123",
                    "first_name": "Ana",
                    "hint_es": "Pregunta por el cobro.",
                    "hint_pt": "Pergunte pela cobrança.",
                }
            ]
        }


class FakeTracer(NullTracer):
    """In-memory stand-in for the tracing surface used by the admin endpoints."""

    def __init__(self, rows=None):
        super().__init__()
        self.rows = rows or []

    async def metrics(self, window_hours=None):
        from app.tracing import aggregate_metrics

        result = aggregate_metrics(self.rows)
        result["tracing_enabled"] = True
        result["window_hours"] = window_hours
        return result

    async def conversation_trace(self, conversation_id):
        return [r for r in self.rows if r.get("conversation_id") == conversation_id]
