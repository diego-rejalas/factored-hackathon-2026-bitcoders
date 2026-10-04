import base64
import json
import os
import time
from datetime import date, datetime, timedelta
from datetime import time as time_of_day
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import Request

from app.migrate import apply_migrations
from app.response_codes import meanings


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

# gold.transactions is a static snapshot (see docs/DATA.md): relative
# day filters are anchored to the latest transaction in the dataset, not now(),
# so the demo does not return an empty list once the snapshot ages.
SNAPSHOT_EDGE_SQL = "select max(transaction_date) as edge from gold.transactions"

TRANSACTION_COLUMNS = """
    transaction_id,
    transaction_date,
    process_date,
    product_id,
    transaction_type,
    transaction_category,
    amount,
    currency,
    coalesce(amount_usd, case when currency = 'USD' then amount end) as amount_usd_effective,
    channel,
    merchant_name,
    merchant_category,
    transaction_country,
    transaction_city,
    transaction_status,
    response_code
"""


DISPUTE_COLUMNS = """
    case_id, customer_id, transaction_id, reason_code, summary, status, evidence, created_at, resolved_at
"""

# product_type is stored in Spanish. A deposit has a balance the customer owns; a credit product has one the
# customer owes. current_balance is shown as stored: the organizer's dictionary does not define it, so for credit
# products "owed" is an inference (7,510 credit products have a balance above their limit, which only makes
# sense if the balance is what is used).
DEPOSIT_TYPES = ("Cuenta Ahorro", "Cuenta Corriente", "Inversión")
CREDIT_TYPES = ("Tarjeta Crédito", "Préstamo Personal", "Préstamo Hipotecario")

# The same columns for a query that joins other tables, where every name has to say which table it is from.
TRANSACTION_COLUMNS_QUALIFIED = """
    t.transaction_id,
    t.transaction_date,
    t.process_date,
    t.product_id,
    t.transaction_type,
    t.transaction_category,
    t.amount,
    t.currency,
    coalesce(t.amount_usd, case when t.currency = 'USD' then t.amount end) as amount_usd_effective,
    t.channel,
    t.merchant_name,
    t.merchant_category,
    t.transaction_country,
    t.transaction_city,
    t.transaction_status,
    t.response_code
"""

PRODUCT_COLUMNS = """
    product_id,
    product_type,
    '****' || right(product_number, 4) as product_number_masked,
    currency,
    current_balance,
    credit_limit,
    interest_rate,
    opening_date,
    product_status,
    days_past_due,
    last_transaction_date
"""


def product_kind(product_type: str) -> str:
    if product_type in DEPOSIT_TYPES:
        return "deposit"
    if product_type in CREDIT_TYPES:
        return "credit"
    return "other"


def encode_cursor(moment: datetime, transaction_id: str) -> str:
    raw = json.dumps([moment.isoformat(), transaction_id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Raises ValueError on anything that is not a cursor this service issued."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        moment, transaction_id = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(moment), str(transaction_id)
    except Exception as error:  # noqa: BLE001
        raise ValueError("invalid cursor") from error


def transaction_row(row: Any) -> dict:
    """A transaction as the API returns it: the row plus the meaning of its response code, when it has one."""
    data = dict(row)
    data["response_meaning"] = meanings(data.get("response_code"))
    return data


def get_store(request: Request) -> "BankStore":
    return request.app.state.store


class BankStore:
    DEMO_CACHE_SECONDS = 300

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._snapshot_edge_value: Any = None
        self._demo_cache: tuple[float, list[dict]] | None = None

    @classmethod
    async def create(cls) -> "BankStore":
        pool = await asyncpg.create_pool(
            host=os.environ["PG_HOST"],
            port=int(os.environ.get("PG_PORT", "5432")),
            user=os.environ["PG_USER"],
            password=os.environ["PG_PASSWORD"],
            database=os.environ.get("PG_DATABASE", "data"),
            init=cls._init_conn,
        )
        return cls(pool)

    @staticmethod
    async def _init_conn(conn: asyncpg.Connection) -> None:
        await conn.set_type_codec(
            "jsonb",
            encoder=lambda value: json.dumps(value, default=_json_default),
            decoder=json.loads,
            schema="pg_catalog",
        )

    async def close(self) -> None:
        await self.pool.close()

    async def init_schema(self) -> list[str]:
        """Apply the pending SQL migrations (app/migrations). Returns the versions it ran."""
        async with self.pool.acquire() as conn:
            return await apply_migrations(conn)

    async def ping(self) -> bool:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("select 1") == 1

    async def snapshot_edge(self) -> Any:
        if self._snapshot_edge_value is None:
            async with self.pool.acquire() as conn:
                self._snapshot_edge_value = await conn.fetchval(SNAPSHOT_EDGE_SQL)
        return self._snapshot_edge_value

    async def authenticate(self, customer_id: str, document_number: str) -> str | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select customer_id
                from gold.customers
                where customer_id = $1
                  and document_number is not null
                  and document_number = $2
                """,
                customer_id,
                document_number,
            )
        return row["customer_id"] if row else None

    async def get_profile(self, customer_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select customer_id, first_name, last_name, country
                from gold.customers
                where customer_id = $1
                """,
                customer_id,
            )
        return dict(row) if row else None

    async def list_transactions(
        self,
        customer_id: str,
        status: str | None = None,
        merchant: str | None = None,
        days: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        sql = f"""
            select {TRANSACTION_COLUMNS}
            from gold.transactions
            where customer_id = $1
        """
        params: list[Any] = [customer_id]
        if status:
            params.append(status)
            sql += f" and transaction_status = ${len(params)}"
        if merchant:
            params.append(f"%{merchant}%")
            sql += f" and merchant_name ilike ${len(params)}"
        if days is not None:
            edge = await self.snapshot_edge()
            params.extend([edge, days])
            sql += (
                f" and transaction_date >= ${len(params) - 1}"
                f" - make_interval(days => ${len(params)})"
            )
        params.append(limit)
        sql += f" order by transaction_date desc limit ${len(params)}"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [transaction_row(row) for row in rows]

    async def get_transaction(self, customer_id: str, transaction_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                select {TRANSACTION_COLUMNS}
                from gold.transactions
                where transaction_id = $1 and customer_id = $2
                """,
                transaction_id,
                customer_id,
            )
        return transaction_row(row) if row else None

    async def create_dispute(
        self,
        customer_id: str,
        transaction_id: str | None,
        reason_code: str,
        summary: str,
        evidence: dict,
    ) -> dict:
        """Open the case, or return the one that already exists for this transaction.

        One case per (customer, transaction), enforced by a unique index (migration 0003): reporting the same
        transaction again is not an error, it is the same case, and two requests at once create one. A case with no
        transaction (an escalation that could not be tied to one) is never a duplicate of another.
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        f"""
                        insert into app.disputes (customer_id, transaction_id, reason_code, summary, evidence)
                        values ($1, $2, $3, $4, $5)
                        returning {DISPUTE_COLUMNS}
                        """,
                        customer_id,
                        transaction_id,
                        reason_code,
                        summary,
                        evidence,
                    )
                    await conn.execute(
                        "insert into app.dispute_events (case_id, event, payload) values ($1, 'created', $2)",
                        row["case_id"],
                        {"reason_code": reason_code},
                    )
            return dict(row)
        except asyncpg.UniqueViolationError:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    select {DISPUTE_COLUMNS} from app.disputes
                    where customer_id = $1 and transaction_id = $2 and status <> 'closed'
                    order by created_at desc limit 1
                    """,
                    customer_id,
                    transaction_id,
                )
            return dict(row)

    async def get_dispute(self, customer_id: str, case_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"select {DISPUTE_COLUMNS} from app.disputes where case_id = $1 and customer_id = $2",
                case_id,
                customer_id,
            )
        return dict(row) if row else None

    async def get_dispute_events(self, case_id: str) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select event, payload, ts
                from app.dispute_events
                where case_id = $1
                order by ts, id
                """,
                case_id,
            )
        return [dict(row) for row in rows]

    async def escalate_dispute(self, customer_id: str, case_id: str, handoff: dict) -> dict | None:
        """Mark the case escalated and keep the handoff. (Not guarded by the current status: see the merge notes.)"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"""
                    update app.disputes
                    set status = 'escalated',
                        evidence = evidence || jsonb_build_object('handoff', $3::jsonb)
                    where case_id = $1 and customer_id = $2
                    returning case_id, customer_id, transaction_id, reason_code,
                              summary, status, evidence, created_at, resolved_at
                    """,
                    case_id,
                    customer_id,
                    handoff,
                )
                if row is not None:
                    await conn.execute(
                        "insert into app.dispute_events (case_id, event, payload) values ($1, 'escalated', $2)",
                        case_id,
                        handoff,
                    )
                    return dict(row)
        return await self.get_dispute(customer_id, case_id)

    # ------------------------------------------------------------------ v1: products, history, summary

    async def list_products(self, customer_id: str) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                select {PRODUCT_COLUMNS} from gold.products
                where customer_id = $1
                order by (product_status = 'Active') desc, product_type, product_id
                """,
                customer_id,
            )
        return [{**dict(row), "kind": product_kind(row["product_type"])} for row in rows]

    async def get_product(self, customer_id: str, product_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"select {PRODUCT_COLUMNS} from gold.products where customer_id = $1 and product_id = $2",
                customer_id,
                product_id,
            )
        return {**dict(row), "kind": product_kind(row["product_type"])} if row else None

    async def list_transactions_page(
        self,
        customer_id: str,
        *,
        product_id: str | None = None,
        status: str | None = None,
        merchant: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[dict], str | None]:
        """Newest first, by keyset (transaction_date, transaction_id): stable while rows are added, unlike OFFSET.

        Each row says whether it already has a dispute case (case_id, dispute_status), so the screen can offer
        "report this charge" or "see my case".
        """
        sql = f"""
            select {TRANSACTION_COLUMNS_QUALIFIED},
                   d.case_id, d.status as dispute_status
            from gold.transactions t
            left join app.disputes d
              on d.customer_id = t.customer_id and d.transaction_id = t.transaction_id and d.status <> 'closed'
            where t.customer_id = $1
        """
        params: list[Any] = [customer_id]

        def add(clause: str, value: Any) -> None:
            nonlocal sql
            params.append(value)
            sql += " and " + clause.format(n=len(params))

        if product_id:
            add("t.product_id = ${n}", product_id)
        if status:
            add("t.transaction_status = ${n}", status)
        if merchant:
            add("t.merchant_name ilike ${n}", f"%{merchant}%")
        if date_from:
            add("t.transaction_date >= ${n}", datetime.combine(date_from, time_of_day.min))
        if date_to:
            add("t.transaction_date < ${n}", datetime.combine(date_to + timedelta(days=1), time_of_day.min))
        if cursor:
            moment, last_id = decode_cursor(cursor)
            params.extend([moment, last_id])
            sql += f" and (t.transaction_date, t.transaction_id) < (${len(params) - 1}, ${len(params)})"
        params.append(limit + 1)
        sql += f" order by t.transaction_date desc, t.transaction_id desc limit ${len(params)}"
        async with self.pool.acquire() as conn:
            rows = [transaction_row(row) for row in await conn.fetch(sql, *params)]
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = encode_cursor(rows[-1]["transaction_date"], rows[-1]["transaction_id"])
        return rows, next_cursor

    async def summary(self, customer_id: str) -> dict:
        """What the home screen shows: balances by currency, the latest movements and the open cases."""
        async with self.pool.acquire() as conn:
            balances = await conn.fetch(
                """
                select currency,
                       case when product_type = any($2) then 'deposit' else 'credit' end as kind,
                       sum(current_balance) as total,
                       count(*) as products
                from gold.products
                where customer_id = $1 and product_status = 'Active'
                  and (product_type = any($2) or product_type = any($3))
                group by 1, 2
                order by 1, 2
                """,
                customer_id,
                list(DEPOSIT_TYPES),
                list(CREDIT_TYPES),
            )
            disputes = await conn.fetch(
                """
                select status, count(*) as total from app.disputes
                where customer_id = $1 and status <> 'closed' group by status
                """,
                customer_id,
            )
        recent, _ = await self.list_transactions_page(customer_id, limit=5)
        return {
            "balances": [dict(row) for row in balances],
            "recent_transactions": recent,
            "disputes": {row["status"]: row["total"] for row in disputes},
        }

    async def list_disputes(
        self, customer_id: str, status: str | None = None, limit: int = 20
    ) -> list[dict]:
        sql = f"select {DISPUTE_COLUMNS} from app.disputes where customer_id = $1 and status <> 'closed'"
        params: list[Any] = [customer_id]
        if status:
            params.append(status)
            sql += f" and status = ${len(params)}"
        params.append(limit)
        sql += f" order by created_at desc, case_id limit ${len(params)}"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ v1: password login

    async def get_credentials(self, username: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select customer_id, username, password_hash, failed_attempts, locked_until
                from app.credentials where lower(username) = lower($1)
                """,
                username,
            )
        return dict(row) if row else None

    async def record_login_failure(self, customer_id: str, max_attempts: int, lock_minutes: int) -> None:
        """Count a failed attempt; the max_attempts-th one locks the account for lock_minutes."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                update app.credentials
                set failed_attempts = failed_attempts + 1,
                    locked_until = case when failed_attempts + 1 >= $2
                                        then now() + make_interval(mins => $3) else locked_until end
                where customer_id = $1
                """,
                customer_id,
                max_attempts,
                lock_minutes,
            )

    async def record_login_success(self, customer_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "update app.credentials set failed_attempts = 0, locked_until = null where customer_id = $1",
                customer_id,
            )

    async def get_customer_names(self, customer_ids: list[str]) -> dict[str, dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "select customer_id, first_name, last_name from gold.customers where customer_id = any($1)",
                customer_ids,
            )
        return {row["customer_id"]: dict(row) for row in rows}

    async def list_demo_accounts(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select c.username, c.demo_label as label, c.demo_hint as hint,
                       g.first_name, g.country
                from app.credentials c join gold.customers g using (customer_id)
                where c.demo_label is not null order by c.demo_label
                """
            )
        return [dict(row) for row in rows]

    async def upsert_credentials(
        self, customer_id: str, username: str, password_hash: str,
        demo_label: str | None = None, demo_hint: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                insert into app.credentials (customer_id, username, password_hash, demo_label, demo_hint)
                values ($1, $2, $3, $4, $5)
                on conflict (customer_id) do update
                set username = excluded.username, password_hash = excluded.password_hash,
                    demo_label = excluded.demo_label, demo_hint = excluded.demo_hint,
                    failed_attempts = 0, locked_until = null, password_changed_at = now()
                """,
                customer_id, username, password_hash, demo_label, demo_hint,
            )
    # --- customer: case list and system resolution -------------------------------------------

    async def list_customer_disputes(self, customer_id: str) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select case_id, transaction_id, reason_code, status, created_at, resolved_at
                from app.disputes
                where customer_id = $1
                order by created_at desc
                """,
                customer_id,
            )
        return [dict(row) for row in rows]

    async def resolve_dispute(
        self, customer_id: str, case_id: str, resolution: str
    ) -> dict | None:
        """System (agent) resolution: 'open' -> 'auto_resolved', guarded so a concurrent
        escalation can never be overwritten. The audit event records who resolved it."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    update app.disputes
                    set status = 'auto_resolved',
                        resolved_at = now()
                    where case_id = $1 and customer_id = $2 and status = 'open'
                    returning case_id, customer_id, transaction_id, reason_code,
                              summary, status, evidence, created_at, resolved_at
                    """,
                    case_id,
                    customer_id,
                )
                if row is not None:
                    await conn.execute(
                        """
                        insert into app.dispute_events (case_id, event, payload)
                        values ($1, 'auto_resolved', $2)
                        """,
                        case_id,
                        {"resolution": resolution, "by": "agent"},
                    )
        return dict(row) if row else None

    # --- admin: disputes inbox ------------------------------------------------------------------

    ADMIN_LIST_SQL = """
        select d.case_id, d.customer_id, d.transaction_id, d.reason_code, d.status,
               d.summary, d.created_at, d.resolved_at,
               c.first_name, c.last_name, c.country,
               d.evidence->'handoff'->>'reason' as handoff_reason,
               d.evidence->'handoff'->>'customer_language' as customer_language
        from app.disputes d
        left join gold.customers c on c.customer_id = d.customer_id
    """

    async def admin_list_disputes(
        self,
        status_filter: str | None = None,
        customer_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        sql = self.ADMIN_LIST_SQL + """
            where (
                $1::text is null
                or ($1::text = 'active' and d.status in ('escalated', 'in_progress'))
                or d.status = $1::text
            )
              and ($2::text is null or d.customer_id = $2::text)
            order by d.created_at desc
            limit $3 offset $4
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, status_filter, customer_id, limit, offset)
        return [dict(row) for row in rows]

    async def admin_count_disputes(
        self, status_filter: str | None = None, customer_id: str | None = None
    ) -> int:
        sql = """
            select count(*)
            from app.disputes d
            where (
                $1::text is null
                or ($1::text = 'active' and d.status in ('escalated', 'in_progress'))
                or d.status = $1::text
            )
              and ($2::text is null or d.customer_id = $2::text)
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql, status_filter, customer_id)

    async def admin_get_dispute(self, case_id: str) -> dict | None:
        sql = self.ADMIN_LIST_SQL + " where d.case_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, case_id)
            if row is None:
                return None
            evidence = await conn.fetchval(
                "select evidence from app.disputes where case_id = $1", case_id
            )
        detail = dict(row)
        detail["evidence"] = evidence or {}
        return detail

    async def admin_transition(
        self,
        case_id: str,
        new_status: str,
        from_statuses: tuple[str, ...],
        event: str,
        payload: dict,
    ) -> dict | None:
        """Guarded update: only fires from the allowed previous statuses, so two admins
        racing on the same case cannot skip the state machine."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    update app.disputes
                    set status = $2,
                        resolved_at = case
                            when $2 = 'closed' then now()
                            when $2 = 'in_progress' then null
                            else resolved_at
                        end
                    where case_id = $1 and status = any($3::text[])
                    returning case_id, customer_id, transaction_id, reason_code,
                              summary, status, evidence, created_at, resolved_at
                    """,
                    case_id,
                    new_status,
                    list(from_statuses),
                )
                if row is not None:
                    await conn.execute(
                        """
                        insert into app.dispute_events (case_id, event, payload)
                        values ($1, $2, $3)
                        """,
                        case_id,
                        event,
                        payload,
                    )
        return dict(row) if row else None

    # --- admin: metrics (definitions mirror docs/CRITERIA.md; denominators always reported) ----

    async def admin_metrics(self, window_hours: int | None = None) -> dict:
        def scope(column: str) -> str:
            return f"and {column} >= now() - make_interval(hours => $1)" if window_hours is not None else ""

        args = (window_hours,) if window_hours is not None else ()
        async with self.pool.acquire() as conn:
            by_status_rows = await conn.fetch(
                f"select status, count(*) as n from app.disputes where true {scope('created_at')} group by status",
                *args,
            )
            escalation_count = await conn.fetchval(
                f"select count(*) from app.disputes where evidence ? 'handoff' {scope('created_at')}",
                *args,
            )
            by_language_rows = await conn.fetch(
                f"""
                select coalesce(evidence->'handoff'->>'customer_language', 'unknown') as language,
                       count(*) as n
                from app.disputes
                where evidence ? 'handoff' {scope('created_at')}
                group by 1 order by n desc
                """,
                *args,
            )
            by_reason_rows = await conn.fetch(
                f"""
                select coalesce(evidence->'handoff'->>'reason', 'unspecified') as reason,
                       count(*) as n
                from app.disputes
                where evidence ? 'handoff' {scope('created_at')}
                group by 1 order by n desc
                """,
                *args,
            )
        by_status = {row["status"]: row["n"] for row in by_status_rows}
        total = sum(by_status.values())
        auto = by_status.get("auto_resolved", 0)
        # Count cases ever handed off, including those subsequently closed by a human.
        escalated = escalation_count or 0
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
            "by_language": [dict(row) for row in by_language_rows],
            "by_reason": [dict(row) for row in by_reason_rows],
        }

    # --- meta: data freshness and deterministic demo scenarios ---------------------------------

    async def data_freshness(self) -> dict:
        async with self.pool.acquire() as conn:
            customers = await conn.fetchval("select count(*) from gold.customers")
            transactions = await conn.fetchval("select count(*) from gold.transactions")
            disputes = await conn.fetchval("select count(*) from app.disputes")
            last_run = await conn.fetchrow(
                "select * from ops.etl_runs order by started_at desc limit 1"
            )
        return {
            "gold": {
                "customers": customers,
                "transactions": transactions,
                "snapshot_edge": await self.snapshot_edge(),
            },
            "app": {"disputes": disputes},
            "last_etl_run": dict(last_run) if last_run else None,
        }

    DEMO_SCENARIO_SQL = """
        with edge as (select max(transaction_date) as e from gold.transactions),
        base as (
            select t.customer_id, t.transaction_status,
                   coalesce(t.amount_usd, case when t.currency = 'USD' then t.amount end) as eff_usd
            from gold.transactions t cross join edge
            where t.transaction_date >= edge.e - interval '90 days'
        ),
        agg as (
            select customer_id,
                   count(*) filter (where transaction_status in ('Declined','Reversed')) as candidates,
                   count(*) filter (where transaction_status in ('Declined','Reversed') and eff_usd is not null and eff_usd < $1) as auto_ok,
                   count(*) filter (where transaction_status in ('Declined','Reversed') and eff_usd >= $1) as over_threshold,
                   count(*) filter (where transaction_status = 'Approved') as approved
            from base group by customer_id
        )
        select scenario, customer_id, document_number, first_name from (
            (select 'auto_resolved' as scenario, a.customer_id
             from agg a join gold.customers c on c.customer_id = a.customer_id
             where a.candidates = 1 and a.auto_ok = 1 and c.document_number is not null
             order by a.customer_id limit 1)
            union all
            (select 'ambiguous', a.customer_id
             from agg a join gold.customers c on c.customer_id = a.customer_id
             where a.candidates >= 3 and c.document_number is not null
             order by a.customer_id limit 1)
            union all
            (select 'fraud', a.customer_id
             from agg a join gold.customers c on c.customer_id = a.customer_id
             where a.approved >= 1 and c.document_number is not null
             order by a.customer_id limit 1)
            union all
            (select 'threshold', a.customer_id
             from agg a join gold.customers c on c.customer_id = a.customer_id
             where a.over_threshold >= 1 and c.document_number is not null
             order by a.customer_id limit 1)
        ) picked join gold.customers using (customer_id)
    """

    DEMO_HINTS = {
        "auto_resolved": {
            "es": "Pregunta por el cobro de {example}: el agente lo verifica y lo resuelve solo.",
            "pt": "Pergunte pela cobrança de {example}: o agente verifica e resolve sozinho.",
        },
        "ambiguous": {
            "es": "Di solo \"tengo un cobro que no reconozco\": hay varias candidatas y el agente pedirá aclarar.",
            "pt": "Diga apenas \"tenho uma cobrança que não reconheço\": há várias candidatas e o agente pedirá esclarecimento.",
        },
        "fraud": {
            "es": "Reporta el cobro aprobado de {example}: siempre escala a revisión humana.",
            "pt": "Reporte a cobrança aprovada de {example}: sempre escala para revisão humana.",
        },
        "threshold": {
            "es": "Pregunta por el cobro de {example}: supera el umbral y escala.",
            "pt": "Pergunte pela cobrança de {example}: supera o limite e escala.",
        },
    }

    def _demo_threshold_usd(self) -> float:
        try:
            return float(os.environ.get("GUARDRAIL_MAX_USD", "500"))
        except ValueError:
            return 500.0

    async def _demo_example_transaction(
        self, customer_id: str, scenario: str, edge: Any, threshold: float
    ) -> dict | None:
        status_filter = {
            "auto_resolved": "transaction_status in ('Declined','Reversed')",
            "ambiguous": "transaction_status in ('Declined','Reversed')",
            "fraud": "transaction_status = 'Approved'",
            "threshold": (
                "transaction_status in ('Declined','Reversed')"
                " and coalesce(amount_usd, case when currency = 'USD' then amount end) >= $3"
            ),
        }[scenario]
        sql = f"""
            select transaction_id, merchant_name, transaction_date, transaction_status,
                   coalesce(amount_usd, case when currency = 'USD' then amount end) as amount_usd_effective
            from gold.transactions
            where customer_id = $1
              and transaction_date >= $2::timestamptz - interval '90 days'
              and {status_filter}
            order by transaction_date desc
            limit 1
        """
        params: list[Any] = [customer_id, edge]
        if scenario == "threshold":
            params.append(threshold)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return dict(row) if row else None

    async def demo_scenarios(self) -> list[dict]:
        """Deterministic demo picks (see plan D5): four customers that guarantee each
        workflow path in a demo/video. Anchored to the same snapshot edge as the agent's
        searches, cached in memory for 5 minutes, and never touching fraud columns."""
        now = time.monotonic()
        if self._demo_cache is not None and now - self._demo_cache[0] < self.DEMO_CACHE_SECONDS:
            return self._demo_cache[1]
        threshold = self._demo_threshold_usd()
        edge = await self.snapshot_edge()
        async with self.pool.acquire() as conn:
            picks = await conn.fetch(self.DEMO_SCENARIO_SQL, threshold)
        scenarios: list[dict] = []
        for pick in picks:
            example = await self._demo_example_transaction(
                pick["customer_id"], pick["scenario"], edge, threshold
            )
            if example is not None:
                amount = example.get("amount_usd_effective")
                amount_text = f"{float(amount):.2f} USD" if amount is not None else None
                merchant = example.get("merchant_name")
                date_text = str(example["transaction_date"])[:10]
                described_es = " ".join(
                    part for part in [
                        amount_text,
                        f"en {merchant}" if merchant else None,
                        f"del {date_text}",
                    ] if part
                )
                described_pt = " ".join(
                    part for part in [
                        amount_text,
                        f"em {merchant}" if merchant else None,
                        f"de {date_text}",
                    ] if part
                )
            else:
                described_es = "los últimos 90 días"
                described_pt = "os últimos 90 dias"
            entry = {
                "scenario": pick["scenario"],
                "customer_id": pick["customer_id"],
                "document_number": pick["document_number"],
                "first_name": pick["first_name"],
                "hint_es": self.DEMO_HINTS[pick["scenario"]]["es"].format(example=described_es),
                "hint_pt": self.DEMO_HINTS[pick["scenario"]]["pt"].format(example=described_pt),
            }
            scenarios.append(entry)
        self._demo_cache = (now, scenarios)
        return scenarios
