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


def _effective_usd(tx: dict):
    if tx.get("amount_usd") is not None:
        return float(tx["amount_usd"])
    if tx.get("currency") == "USD":
        return float(tx["amount"])
    return None


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
            "created_at": datetime(2026, 9, 30, 12, 0, 0) + timedelta(minutes=self._seq),
            "resolved_at": None,
        }
        self.disputes[case_id] = dispute
        self.events[case_id] = [
            {"event": "created", "payload": {"reason_code": reason_code}, "ts": datetime(2026, 9, 30, 12, 0, 0)}
        ]
        return dict(dispute)

    async def get_dispute(self, customer_id: str, case_id: str):
        dispute = self.disputes.get(case_id)
        if dispute is None or dispute["customer_id"] != customer_id:
            return None
        return dict(dispute)

    async def get_dispute_events(self, case_id: str):
        return [dict(e) for e in self.events.get(case_id, [])]

    async def escalate_dispute(self, customer_id: str, case_id: str, handoff: dict):
        dispute = self.disputes.get(case_id)
        if dispute is None or dispute["customer_id"] != customer_id:
            return None
        dispute["status"] = "escalated"
        dispute["evidence"] = {**dispute["evidence"], "handoff": handoff}
        self.events[case_id].append({"event": "escalated", "payload": handoff, "ts": datetime(2026, 9, 30, 12, 5, 0)})
        return dict(dispute)

    async def list_customer_disputes(self, customer_id: str):
        rows = [d for d in self.disputes.values() if d["customer_id"] == customer_id]
        rows.sort(key=lambda d: d["created_at"], reverse=True)
        return [
            {
                "case_id": d["case_id"],
                "transaction_id": d["transaction_id"],
                "reason_code": d["reason_code"],
                "status": d["status"],
                "created_at": d["created_at"],
                "resolved_at": d["resolved_at"],
            }
            for d in rows
        ]

    async def resolve_dispute(self, customer_id: str, case_id: str, resolution: str):
        dispute = self.disputes.get(case_id)
        if dispute is None or dispute["customer_id"] != customer_id or dispute["status"] != "open":
            return None
        dispute["status"] = "auto_resolved"
        dispute["resolved_at"] = datetime(2026, 9, 30, 12, 1, 0)
        self.events[case_id].append(
            {"event": "auto_resolved", "payload": {"resolution": resolution, "by": "agent"}, "ts": datetime(2026, 9, 30, 12, 1, 0)}
        )
        return dict(dispute)

    def _admin_row(self, dispute: dict) -> dict:
        customer = self.customers.get(dispute["customer_id"], {})
        handoff = (dispute.get("evidence") or {}).get("handoff") or {}
        return {
            "case_id": dispute["case_id"],
            "customer_id": dispute["customer_id"],
            "transaction_id": dispute["transaction_id"],
            "reason_code": dispute["reason_code"],
            "status": dispute["status"],
            "summary": dispute["summary"],
            "created_at": dispute["created_at"],
            "resolved_at": dispute["resolved_at"],
            "first_name": customer.get("first_name"),
            "last_name": customer.get("last_name"),
            "country": customer.get("country"),
            "handoff_reason": handoff.get("reason"),
            "customer_language": handoff.get("customer_language"),
        }

    async def admin_list_disputes(self, status_filter=None, customer_id=None, limit=50, offset=0):
        rows = [self._admin_row(d) for d in self.disputes.values()]
        if status_filter:
            rows = [
                r for r in rows
                if (r["status"] in ("escalated", "in_progress") if status_filter == "active" else r["status"] == status_filter)
            ]
        if customer_id:
            rows = [r for r in rows if r["customer_id"] == customer_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows[offset : offset + limit]

    async def admin_count_disputes(self, status_filter=None, customer_id=None):
        return len(await self.admin_all_disputes(status_filter, customer_id))

    async def admin_all_disputes(self, status_filter=None, customer_id=None):
        rows = [self._admin_row(d) for d in self.disputes.values()]
        if status_filter:
            rows = [
                r for r in rows
                if (r["status"] in ("escalated", "in_progress") if status_filter == "active" else r["status"] == status_filter)
            ]
        if customer_id:
            rows = [r for r in rows if r["customer_id"] == customer_id]
        return rows

    async def admin_get_dispute(self, case_id: str):
        dispute = self.disputes.get(case_id)
        if dispute is None:
            return None
        row = self._admin_row(dispute)
        row["evidence"] = dispute["evidence"]
        return row

    async def admin_transition(self, case_id, new_status, from_statuses, event, payload):
        dispute = self.disputes.get(case_id)
        if dispute is None or dispute["status"] not in from_statuses:
            return None
        dispute["status"] = new_status
        if new_status == "closed":
            dispute["resolved_at"] = datetime(2026, 9, 30, 13, 0, 0)
        self.events[case_id].append({"event": event, "payload": payload, "ts": datetime(2026, 9, 30, 13, 0, 0)})
        row = self._admin_row(dispute)
        row["evidence"] = dispute["evidence"]
        return row

    async def admin_metrics(self, window_hours=None):
        by_status: dict[str, int] = {}
        for dispute in self.disputes.values():
            by_status[dispute["status"]] = by_status.get(dispute["status"], 0) + 1
        total = sum(by_status.values())
        auto = by_status.get("auto_resolved", 0)
        escalated = sum(
            1 for dispute in self.disputes.values()
            if (dispute.get("evidence") or {}).get("handoff")
        )
        by_language: dict[str, int] = {}
        by_reason: dict[str, int] = {}
        for dispute in self.disputes.values():
            handoff = (dispute.get("evidence") or {}).get("handoff")
            if handoff:
                language = handoff.get("customer_language", "unknown")
                by_language[language] = by_language.get(language, 0) + 1
                reason = handoff.get("reason", "unspecified")
                by_reason[reason] = by_reason.get(reason, 0) + 1
        return {
            "window_hours": window_hours,
            "total_cases": total,
            "by_status": by_status,
            "safe_automated_resolution": {
                "resolved": auto,
                "attempted": total,
                "rate_percent": round(100.0 * auto / total, 1) if total else None,
            },
            "escalations": {
                "count": escalated,
                "rate_percent": round(100.0 * escalated / total, 1) if total else None,
            },
            "human_closure": {"closed": by_status.get("closed", 0)},
            "by_language": [{"language": k, "n": v} for k, v in by_language.items()],
            "by_reason": [{"reason": k, "n": v} for k, v in by_reason.items()],
        }

    async def data_freshness(self):
        return {
            "gold": {
                "customers": len(self.customers),
                "transactions": len(self.transactions),
                "snapshot_edge": max(t["transaction_date"] for t in self.transactions.values()),
            },
            "app": {"disputes": len(self.disputes)},
            "last_etl_run": {
                "run_id": "manual__2026-06-18",
                "status": "success",
            },
        }

    async def demo_scenarios(self):
        edge = max(t["transaction_date"] for t in self.transactions.values())
        window = [t for t in self.transactions.values() if t["transaction_date"] >= edge - timedelta(days=90)]
        agg: dict[str, dict] = {}
        for tx in window:
            stats = agg.setdefault(
                tx["customer_id"],
                {"candidates": 0, "auto_ok": 0, "over_threshold": 0, "approved": 0},
            )
            if tx["transaction_status"] in ("Declined", "Reversed"):
                stats["candidates"] += 1
                eff = _effective_usd(tx)
                if eff is not None and eff < 500:
                    stats["auto_ok"] += 1
                elif eff is not None:
                    stats["over_threshold"] += 1
            if tx["transaction_status"] == "Approved":
                stats["approved"] += 1
        picks = []
        for scenario, predicate in (
            ("auto_resolved", lambda s: s["candidates"] == 1 and s["auto_ok"] == 1),
            ("ambiguous", lambda s: s["candidates"] >= 3),
            ("fraud", lambda s: s["approved"] >= 1),
            ("threshold", lambda s: s["over_threshold"] >= 1),
        ):
            for customer_id in sorted(agg):
                customer = self.customers.get(customer_id)
                if customer and customer.get("document_number") and predicate(agg[customer_id]):
                    picks.append((scenario, customer_id))
                    break
        scenarios = []
        for scenario, customer_id in picks:
            customer = self.customers[customer_id]
            statuses = ("Approved",) if scenario == "fraud" else ("Declined", "Reversed")
            examples = [
                t
                for t in window
                if t["customer_id"] == customer_id and t["transaction_status"] in statuses
            ]
            examples.sort(key=lambda t: t["transaction_date"], reverse=True)
            example = _with_effective_usd(dict(examples[0])) if examples else None
            if example:
                amount = example.get("amount_usd_effective")
                described = " ".join(
                    part
                    for part in [
                        f"{float(amount):.2f} USD" if amount is not None else None,
                        f"en {example['merchant_name']}" if example.get("merchant_name") else None,
                        f"del {example['transaction_date'].date().isoformat()}",
                    ]
                    if part
                )
            else:
                described = "los últimos 90 días"
            scenarios.append(
                {
                    "scenario": scenario,
                    "customer_id": customer_id,
                    "document_number": customer["document_number"],
                    "first_name": customer["first_name"],
                    "hint_es": f"Pregunta por el cobro de {described} ({scenario}).",
                    "hint_pt": f"Pergunte pela cobrança de {described} ({scenario}).",
                }
            )
        return scenarios
